'''FPVScores Plugin'''

import logging
logger = logging.getLogger(__name__)
#import RHUtils
import json
from sqlalchemy.ext.declarative import DeclarativeMeta
from data_export import DataExporter
from eventmanager import Evt

from RHUI import UIField, UIFieldType, UIFieldSelectOption


import requests


from flask import templating
from flask.blueprints import Blueprint



# Read the JSON file
with open('plugins/fpvscores/static/assets/data/countries.json', 'r') as file:
    countries_data = json.load(file)
options = []
for country in countries_data:
    code = country["alpha2"]
    name = country["name"]
    option = UIFieldSelectOption(code, name)
    options.append(option)
options.sort(key=lambda x: x.label)
country_ui_field = UIField('country', "Country Code", UIFieldType.SELECT, options=options, value="")

def register_handlers(args):
    if 'register_fn' in args:
        for exporter in discover():
            args['register_fn'](exporter)

def initialize(rhapi):
    rhapi.fields.register_pilot_attribute( country_ui_field )

    rhapi.fields.register_pilot_attribute( UIField('safetycheck', "Safety Checked", UIFieldType.CHECKBOX) )
    rhapi.fields.register_pilot_attribute( UIField('fpvs_uuid', "FPVS Pilot UUID", UIFieldType.TEXT) )

    rhapi.fields.register_pilot_attribute( UIField('comm_elrs', "ELRS Passphrase", UIFieldType.TEXT) )
    rhapi.fields.register_pilot_attribute( UIField('comm_fusion', "Fusion Mac", UIFieldType.TEXT) )

    rhapi.ui.register_panel("fpvscores_run", "FPV Scores", "format")
    rhapi.fields.register_option( UIField('event_uuid', "Event UUID", UIFieldType.TEXT), 'fpvscores_run' )
    #rhapi.ui.register_quickbutton("fpvscores_run", "fpvscores_upload", "Upload Scores to FPVScores.com", runUploadBtn)
    rhapi.ui.register_quickbutton("fpvscores_run", "fpvscores_upload", "Upload Scores to FPVScores.com", runUploadBtn, {'rhapi': rhapi})

    rhapi.events.on(Evt.DATA_EXPORT_INITIALIZE, register_handlers)
    #rhapi.events.on(Evt.DATABASE_EXPORT, uploadToFPVS) 

    bp = Blueprint(
        'fpvscores',
        __name__,
        template_folder='pages',
        static_folder='static',
        static_url_path='/fpvscores/static'
    )

    @bp.route('/fpvscores')
    def fpscoresPage():
        return templating.render_template('fpvscores.html')
    @bp.route('/qr_scanner')
    def qrScannerPage():
        return templating.render_template('qr_scanner.html')
    @bp.route('/overlay_topbar')
    def overlayTopbarPage():
        #return templating.render_template('stream_topbar.html')     
        return templating.render_template('stream_topbar.html', serverInfo=None, getOption=rhapi.db.option, __=rhapi.__, DEBUG=False)
    rhapi.ui.blueprint_add(bp)

def write_json(data):
    payload = json.dumps(data, indent='\t', cls=AlchemyEncoder)

    return {
        'data': payload,
        'encoding': 'application/json',
        'ext': 'json'
    }

def runUploadBtn(args):
    print('run upload by frontend button')
    args['rhapi'].ui.message_notify('Import Started')
    data = args['rhapi'].io.run_export('JSON_FPVScores_Upload')
    #print(data)
    uploadToFPVS_frombtn(args, data)


## FPV Scores Upload Data
def uploadToFPVS(args):
    json_data = args['data']
    print('upload results to FPVScores.com')   
    
    url = 'https://api.fpvscores.com/rh/0.0.1/?action=rh_push'

    headers = {'Authorization' : 'rhconnect', 'Accept' : 'application/json', 'Content-Type' : 'application/json'}
    r = requests.post(url, data=json_data, headers=headers)
    #print(r.status_code)
    #print(r.text)
    if r.status_code == 200:
        if r.text == 'no import!':
            args['rhapi'].ui.message_notify('FPV Scores: No Import File Found')
        elif r.text == 'no event found':
            args['rhapi'].ui.message_notify('FPV Scores: No Matching Event Found - Check your UUID')
        else:
            args['rhapi'].ui.message_notify(r.text)


## FPV Scores Upload Data
def uploadToFPVS_frombtn(args, input_data):
    print('upload results to FPVScores.com')   

    json_data =  input_data['data']

    print(json_data)
    
    url = 'https://api.fpvscores.com/rh/0.0.1/?action=rh_push'

    headers = {'Authorization' : 'rhconnect', 'Accept' : 'application/json', 'Content-Type' : 'application/json'}
    r = requests.post(url, data=json_data, headers=headers)
    #print(r.status_code)
    #print(r.text)
    if r.status_code == 200:
        if r.text == 'no import!':
            args['rhapi'].ui.message_notify('FPV Scores: No Import File Found')
        elif r.text == 'no event found':
            args['rhapi'].ui.message_notify('FPV Scores: No Matching Event Found - Check your UUID')
        else:
            args['rhapi'].ui.message_notify(r.text)       
    

def assemble_fpvscoresUpload(rhapi):
    payload = {}
    payload['import_settings'] = 'upload_FPVScores'
    payload['Pilot'] = assemble_pilots_complete(rhapi)
    payload['Heat'] = assemble_heats_complete(rhapi)
    payload['HeatNode'] = assemble_heatnodes_complete(rhapi)
    payload['RaceClass'] = assemble_classes_complete(rhapi)
    #payload['RaceFormat'] = assemble_formats_complete(RHData, PageCache)
    #payload['SavedRaceMeta'] = assemble_racemeta_complete(RHData, PageCache)
    #payload['SavedPilotRace'] = assemble_pilotrace_complete(RHData, PageCache)
    #payload['SavedRaceLap'] = assemble_racelap_complete(RHData, PageCache)
    #payload['Results'] = assemble_results(RHData, PageCache)
    payload['GlobalSettings'] = assemble_settings_complete(rhapi)
    
    payload['FPVScores_results'] = rhapi.eventresults.results

    return payload

    
    

def discover(*args, **kwargs):
    # returns array of exporters with default arguments
    return [
        DataExporter(
            'JSON FPVScores Upload',
            write_json,
            assemble_fpvscoresUpload
        )
    ]

def assemble_results_raw(RaceContext):
    payload = RaceContext.pagecache.get_cache()
    return payload


def assemble_pilots_complete(rhapi):
    payload = rhapi.db.pilots

    for pilot in payload:
        pilot.fpvsuuid = rhapi.db.pilot_attribute_value(pilot.id, 'fpvs_uuid')
        pilot.country = rhapi.db.pilot_attribute_value(pilot.id, 'country')
        #print( vars(pilot) )

    return payload


def assemble_heats_complete(rhapi):
    payload = rhapi.db.heats
    return payload

def assemble_heatnodes_complete(rhapi):
    payload = rhapi.db.slots
    return payload

def assemble_classes_complete(rhapi):
    payload = rhapi.db.raceclasses
    return payload

def assemble_formats_complete(rhapi):
    payload = rhapi.db.raceformats
    return payload

def assemble_racemeta_complete(rhapi):
    payload = rhapi.db.races
    return payload

def assemble_pilotrace_complete(rhapi):
    payload = rhapi.db.pilotruns
    return payload

def assemble_racelap_complete(rhapi):
    payload = rhapi.db.laps
    return payload

def assemble_profiles_complete(rhapi):
    payload = rhapi.db.frequencysets
    return payload

def assemble_settings_complete(rhapi):
    payload = rhapi.db.options
    return payload

class AlchemyEncoder(json.JSONEncoder):
    def default(self, obj):  #pylint: disable=arguments-differ
        if isinstance(obj.__class__, DeclarativeMeta):
            # an SQLAlchemy class
            mapped_instance = inspect(obj)
            fields = {}
            for field in mapped_instance.attrs.keys():
                data = obj.__getattribute__(field)
                if field != 'query' \
                    and field != 'query_class':
                    try:
                        json.dumps(data) # this will fail on non-encodable values, like other classes
                        if field == 'frequencies':
                            fields[field] = json.loads(data)
                        elif field == 'enter_ats' or field == 'exit_ats':
                            fields[field] = json.loads(data)
                        else:
                            fields[field] = data
                    except TypeError:
                        fields[field] = None
            # a json-encodable dict
            return fields

        return json.JSONEncoder.default(self, obj)
