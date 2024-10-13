'''FPVScores Plugin'''

import logging
logger = logging.getLogger(__name__)
#import RHUtils
import json
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy import inspect
from data_export import DataExporter
from eventmanager import Evt
from EventActions import ActionEffect

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
    rhapi.ui.register_panel("fpvscores_format", "FPV Scores", "format")
    rhapi.ui.register_panel("fpvscores_run", "FPV Scores", "run")

    rhapi.fields.register_option( UIField('event_uuid', "Event UUID", UIFieldType.TEXT), 'fpvscores_format' )
    rhapi.fields.register_option( UIField('auto_upload', "Auto Upload to FPV Scores", UIFieldType.CHECKBOX), 'fpvscores_format' )
    rhapi.ui.register_quickbutton("fpvscores_format", "fpvscores_upload", "Upload Scores to FPVScores.com", runUploadBtn, {'rhapi': rhapi})
    rhapi.ui.register_quickbutton("fpvscores_run", "fpvscores_upload_run", "Upload Scores to FPVScores.com", runUploadBtn, {'rhapi': rhapi})
    rhapi.ui.register_quickbutton("fpvscores_format", "fpvscores_clear", "Clear event data on FPVScores.com", runClearBtn, {'rhapi': rhapi})

    rhapi.events.on(Evt.DATA_EXPORT_INITIALIZE, register_handlers)
    rhapi.events.on(Evt.LAPS_SAVE, auto_upload, {'rhapi': rhapi})


    bp = Blueprint(
        'fpvscores',
        __name__,
        template_folder='pages',
        static_folder='static',
        static_url_path='/fpvscores/static'
    )

    @bp.route('/fpvscores')
    def fpscoresPage():
        return templating.render_template('fpvscores.html', serverInfo=None, getOption=rhapi.db.option, __=rhapi.__)
    @bp.route('/fpvscores/qr_scanner')
    def qrScannerPage():
        return templating.render_template('qr_scanner.html', serverInfo=None, getOption=rhapi.db.option, __=rhapi.__)

    rhapi.ui.blueprint_add(bp)

def auto_upload(args):
    if args['rhapi'].db.option("auto_upload") == '1':
        print("Attempting to upload to fpvscores...")
        data = args['rhapi'].io.run_export('JSON_FPVScores_Upload')
        uploadToFPVS(args, data, False)

def write_json(data):
    payload = json.dumps(data, indent='\t', cls=AlchemyEncoder)

    return {
        'data': payload,
        'encoding': 'application/json',
        'ext': 'json'
    }

def runUploadBtn(args):
    #print('run upload by frontend button')
    args['rhapi'].ui.message_notify(args['rhapi'].__('Event data upload started.'))
    data = args['rhapi'].io.run_export('JSON_FPVScores_Upload')
    #print(data)
    uploadToFPVS(args, data, True)


def runClearBtn(args):
    #print('run clear by frontend button')
    args['rhapi'].ui.message_notify(args['rhapi'].__('Clear event data request has been send.'))
    url = 'https://api.fpvscores.com/rh/0.0.2/?action=rh_clear'
    json_data = '{"event_uuid":"' + args['rhapi'].db.option('event_uuid') + '"}'
    headers = {'Authorization' : 'rhconnect', 'Accept' : 'application/json', 'Content-Type' : 'application/json'}
    r = requests.post(url, data=json_data, headers=headers)
    if r.status_code == 200:
        if r.text == 'no event found':
            args['rhapi'].ui.message_notify(args['rhapi'].__('No event found. Check your event UUID on FPVScores.com.'))
        elif r.text == 'Data Cleared':
            args['rhapi'].ui.message_notify(args['rhapi'].__('Event data is cleared on FPVScores.com.'))
        else:
            args['rhapi'].ui.message_notify(r.text)



## FPV Scores Upload Data
def uploadToFPVS(args, input_data, button_press):
    #print('upload results to FPVScores.com')   
    json_data =  input_data['data']
    url = 'https://api.fpvscores.com/rh/0.0.3/?action=mgp_push'
    headers = {'Authorization' : 'rhconnect', 'Accept' : 'application/json', 'Content-Type' : 'application/json'}
    r = requests.post(url, data=json_data, headers=headers)
    #print(r.status_code)
    #print(r.text)
    if r.status_code == 200:
        if r.text == 'no import!':
            args['rhapi'].ui.message_notify(args['rhapi'].__('No import data found, add data (pilots, classes, heats) first.'))
        elif r.text == 'no event found':
            args['rhapi'].ui.message_notify(args['rhapi'].__('No event found - Check your event UUID on FPVScores.com.'))
        elif 'Import Succesful' in r.text:
            if button_press:
                args['rhapi'].ui.message_notify(args['rhapi'].__('Uploaded data successfully.'))
        logger.info(r.text)   
    

def assemble_fpvscoresUpload(rhapi):
    payload = {}
    payload['import_settings'] = 'upload_FPVScores'
    payload['Pilot'] = assemble_pilots_complete(rhapi)
    payload['Heat'] = assemble_heats_complete(rhapi)
    payload['HeatNode'] = assemble_heatnodes_complete(rhapi)
    payload['RaceClass'] = assemble_classes_complete(rhapi)
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
    return payload


def assemble_heats_complete(rhapi):
    payload = rhapi.db.heats
    return payload

def assemble_heatnodes_complete(rhapi):
    payload = rhapi.db.slots
    
    freqs = json.loads(rhapi.race.frequencyset.frequencies)
    
    for slot in payload:
        if slot.node_index is not None and isinstance(slot.node_index, int):
            slot.node_frequency_band = freqs['b'][slot.node_index] if len(freqs['b']) > slot.node_index else ' '
            slot.node_frequency_c = freqs['c'][slot.node_index] if len(freqs['c']) > slot.node_index else ' '
            slot.node_frequency_f = freqs['f'][slot.node_index] if len(freqs['f']) > slot.node_index else ' '
        else:
            # Als slot.node_index None is of geen integer, gebruik dan een lege string als de waarde
            slot.node_frequency_band = ' '
            slot.node_frequency_c = ' '
            slot.node_frequency_f = ' '
        
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
        custom_vars = ['fpvsuuid','country','node_frequency_band','node_frequency_c','node_frequency_f']
        if isinstance(obj.__class__, DeclarativeMeta):
            # an SQLAlchemy class
            mapped_instance = inspect(obj)
            fields = {}
            for field in dir(obj): 
                if field in [*mapped_instance.attrs.keys(), *custom_vars]:
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
