# -*- coding: utf-8 -*-
import codecs
import os
import sys
import subprocess
import time
import xml.etree.ElementTree as ET
from multiprocessing import Process
from subprocess import PIPE, STDOUT

from flask import Flask
from flask import jsonify, request, json
from flask import render_template, send_file
from werkzeug.utils import secure_filename

import flask_config

class CustomFlask(Flask):
    jinja_options = Flask.jinja_options.copy()
    jinja_options.update(dict(
      block_start_string='{%',
      block_end_string='%}',
      variable_start_string='((',
      variable_end_string='))',
      comment_start_string='{#',
      comment_end_string='#}',
    ))


app = CustomFlask(__name__)

#--------------------------------------------------------------
#   method
#--------------------------------------------------------------
def path_to_dict(path):
    '''
        get file tree

        directory:
            {
                name: (str),
                path: (str),
                type: directory,
                children: (list)
            }
        file:
            {
                name: (str),
                path: (str),
                type: file,
                content: (str),
                modification_content: (str)
            }
    '''
    dict_dir = {
        'name': os.path.basename(path),
        'path': path
    }
    if os.path.isdir(path):
        dict_dir.update({
            'type': "directory",
            'children': [path_to_dict(os.path.join(path, _dir)) for _dir in os.listdir(path)]
        })
    else:
        dict_dir['type'] = "file"
        file_content = ''
        with codecs.open(path, 'r', encoding="iso-8859-15") as f:
            for line in f:
                file_content += line.rstrip() + '\n'
        dict_dir['content'] = file_content
        dict_dir['modification_content'] = file_content
    return dict_dir


def build_apk():
    '''
        build new apk file
    '''
    apktool_format = "\"{apktool_path}\" b {unpack_dir_path}" \
        .format(apktool_path=flask_config.apktool_path, 
                unpack_dir_path=flask_config.unpack_dir_path)

    ret_mes = str(subprocess.check_output(apktool_format, shell=True))
    if 'ERROR' in ret_mes:
        print("Error", ret_mes)
        return False


def create_keystore(dict_keystore_data):
    keytool_format = \
        ("\"{java_path}\keytool\" -genkey -v -keyalg DSA -keysize 1024 -sigalg SHA1withDSA -validity 20000 " + \
        "-keystore {keystore_path} -alias {alias} -keypass {keypass} -storepass {storepass}") \
        .format(java_path=flask_config.java_path,
                keystore_path=flask_config.keystore_path,
                alias=dict_keystore_data['alias'],
                keypass=dict_keystore_data['keypass'],
                storepass=dict_keystore_data['storepass'])

    keytool_keystore_info_format = \
        "{common_name}\n{organization_unit}\n{organization_name}\n{locality_name}\n{state_name}\n{country}\ny\n" \
        .format(common_name=dict_keystore_data['common_name'],
                organization_unit=dict_keystore_data['organization_unit'],
                organization_name=dict_keystore_data['organization_name'],
                locality_name=dict_keystore_data['locality_name'],
                state_name=dict_keystore_data['state_name'],
                country=dict_keystore_data['country'])
    
    p = subprocess.Popen(keytool_format, stdout=PIPE, stdin=PIPE, stderr=STDOUT)
    
    out = p.communicate(input=keytool_keystore_info_format.encode())[0]
    if 'Exception' in str(out):
        print("Exception", out.decode('UTF-8', 'strict'))
        return False
    else:
        print("create keystore success!")


def sign_apk():
    jarsigner_format = \
        ("\"{java_path}\jarsigner\" -tsa http://timestamp.digicert.com -verbose -sigalg SHA1withDSA -digestalg SHA1 " + \
        "-keystore {keystore_path} -storepass {storepass} \"{apk_file_path}\" {alias}") \
        .format(java_path=flask_config.java_path,
                keystore_path=flask_config.keystore_path,
                storepass=flask_config.keystore_storepass,
                apk_file_path=flask_config.new_apk_file_path,
                alias=flask_config.keystore_alias)
                
    p = subprocess.Popen(jarsigner_format, stdout=PIPE, stdin=PIPE, stderr=STDOUT)
    out = p.communicate()[0]
    if 'jar signed' in str(out):
        print("Success!")
        return True
    else:
        print("Error", out.decode('UTF-8', 'strict'))
        return False


def unpack_apk():
    apktool_format = "\"{apktool_path}\" d -f {apk_file_path} -o {unpack_dir_path}" \
        .format(apktool_path=flask_config.apktool_path, 
                apk_file_path=flask_config.apk_file_path,
                unpack_dir_path=flask_config.unpack_dir_path)

    ret_mes = str(subprocess.check_output(apktool_format, shell=True))
    if 'ERROR' in ret_mes:
        print("Error", ret_mes)
        return False
        
    z7za_path_format = "\"{z7za_path}\" e -y {apk_file_path} classes.dex -o{classes_dir_path}" \
        .format(z7za_path=flask_config.z7za_path, 
                apk_file_path=flask_config.apk_file_path,
                classes_dir_path=flask_config.classes_dir_path)

    ret_mes = str(subprocess.check_output(z7za_path_format, shell=True))
    if 'Error' in str(ret_mes) or 'ERROR' in str(ret_mes):
        print("Error", str(ret_mes))
        return False
    else:
        print("extract classes.dex success!")
        
    dex2jar_path_format = "\"{dex2jar_path}\" -f {classes_dir_path}\classes.dex -o {classes_dir_path}\classes.jar" \
        .format(dex2jar_path=flask_config.dex2jar_path,
                classes_dir_path=flask_config.classes_dir_path)
    ret_mes = str(subprocess.check_output(dex2jar_path_format, shell=True))
    return True


def move_apk_to_dist_dir():
    mkdir_dist_format = "mkdir {unpack_dir_path}\\dist" \
        .format(unpack_dir_path=flask_config.unpack_dir_path)

    ret_mes = subprocess.check_output(mkdir_dist_format, shell=True)

    copy_apk_to_dist_format = "copy {apk_file_path} {unpack_dir_path}\dist\." \
        .format(apk_file_path=flask_config.apk_file_path,
                unpack_dir_path=flask_config.unpack_dir_path)

    ret_mes = subprocess.check_output(copy_apk_to_dist_format, shell=True)

    flask_config.new_apk_file_path = "{unpack_dir_path}\dist\{apk_name}.apk" \
        .format(unpack_dir_path=flask_config.unpack_dir_path, 
                apk_name=flask_config.apk_name)


def read_package_name():
    tree = ET.parse(flask_config.android_manifest_xml_path)
    root = tree.getroot()
    flask_config.package_name = root.attrib['package']


def start_emulator_device(device):
    open_emulator_format = "\"{emulator_path}\" -avd {device} -netdelay none -netspeed full" \
	    .format(emulator_path=flask_config.emulator_path, 
                device=device)
    proc = subprocess.Popen(open_emulator_format, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in proc.stdout:
        str_line = line.decode('UTF-8', 'strict')
        if 'Serial number of this emulator (for ADB): ' in str_line:
            emulator_name = str_line.strip().split('Serial number of this emulator (for ADB): ')[-1]
            break

    #p = Process(target=wait_emulator_and_start_get_log(emulator_name))
    #p.start()
    

def wait_emulator_and_start_get_log(emulator_name):
    adb_list_format = "\"{adb_path}\" devices" \
        .format(adb_path=flask_config.adb_path)
    count = 60 * 1
    while count:
        ret_mes = subprocess.check_output(adb_list_format, shell=True)
        device_list = [device.split('\t')[0].strip() for device in ret_mes.decode('utf-8').split('\n') \
            if device.strip() and len(device.split('\t')) == 2 and 'device' in device.split('\t')[-1]]
        if emulator_name in device_list:
            p = Process(target=get_log_of_emulator(emulator_name))
            p.start()
            break
        time.sleep(5)
        count -= 1

def start_vnc_of_emulator(device):
    push_vnc_format = "\"{adb_path}\" -s {device} push {androidvncserver_path} {emulator_androidvncserver_path}" \
        .format(adb_path=flask_config.adb_path,
                device=device,
                androidvncserver_path=flask_config.androidvncserver_path,
                emulator_androidvncserver_path=flask_config.emulator_androidvncserver_path)
    ret_mes = subprocess.check_output(push_vnc_format, shell=True)

    chmod_775_format = "\"{adb_path}\" -s {device} shell chmod 775 {emulator_androidvncserver_path}" \
        .format(adb_path=flask_config.adb_path,
                device=device,
                emulator_androidvncserver_path=emulator_androidvncserver_path)
    ret_mes = subprocess.check_output(chmod_775_format, shell=True)

    forward_tcp_5901_format = "\"{adb_path}\" -s {device} forward tcp:5901 tcp:5901" \
        .format(adb_path=flask_config.adb_path,
                device=device)
    ret_mes = subprocess.check_output(forward_tcp_5901_format, shell=True)

    forward_tcp_5801_format = "\"{adb_path}\" -s {device} forward tcp:5801 tcp:5801" \
        .format(adb_path=flask_config.adb_path,
                device=device)
    ret_mes = subprocess.check_output(forward_tcp_5801_format, shell=True)

    start_vnc_format = "\"{adb_path}\" -s {device} shell ./{emulator_androidvncserver_path}" \
        .format(adb_path=flask_config.adb_path,
                device=device,
                emulator_androidvncserver_path=emulator_androidvncserver_path)
    subprocess.Popen(start_vnc_format, shell=True,
             stdin=None, stdout=None, stderr=None, close_fds=True)


def get_log_of_emulator(device):
    print("get_log")
    get_log_format = "\"{adb_path}\" -s {device} logcat" \
        .format(adb_path=flask_config.adb_path,
                device=device)

    CREATE_NO_WINDOW = 0x08000000

    with open(flask_config.log_file_path, 'w') as f:
        proc = subprocess.Popen(get_log_format,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW)
        for line in proc.stdout:
            f.write(line.decode('UTF-8', 'strict'))
            f.flush()
        proc.kill()

#--------------------------------------------------------------
#   api
#--------------------------------------------------------------
@app.route('/api/treeData', methods=['GET'])
def treeData():
    return jsonify(flask_config.treeData)


@app.route('/api/getEmulatorDevices', methods=['GET'])
def getEmulatorDevices():
    emulator_list_format = "\"{emulator_path}\" -list-avds" \
        .format(emulator_path=flask_config.emulator_path)

    ret_mes = subprocess.check_output(emulator_list_format, shell=True)
    device_list = [device.strip() for device in ret_mes.decode('utf-8').split('\n') if device]
    return_devices_list = []
    for idx, device in enumerate(device_list):
        return_devices_list.append({
            "idx": idx,
            "device": device})
    return jsonify(return_devices_list)


@app.route('/api/startEmulatorDevices', methods=['POST'])
def startEmulatorDevices():
    device = str(request.data,'utf-8')
    p = Process(target=start_emulator_device(device))
    p.start()
    return jsonify()


@app.route('/api/getStartEmulatorDevices', methods=['GET'])
def getStartEmulatorDevices():
    adb_list_format = "\"{adb_path}\" devices" \
        .format(adb_path=flask_config.adb_path)

    ret_mes = subprocess.check_output(adb_list_format, shell=True)

    device_list = [device.split('\t')[0].strip() for device in ret_mes.decode('utf-8').split('\n') \
        if device.strip() and len(device.split('\t')) == 2 and 'device' in device.split('\t')[-1]]
    return_start_devices_list = []
    for idx, device in enumerate(device_list):
        return_start_devices_list.append({
            'idx': idx,
            'device': device
        })
    return jsonify(return_start_devices_list)


@app.route('/api/installAPK', methods=['PUT'])
def installAPK():
    device = str(request.data, 'utf-8')
    uninstall_format = "\"{adb_path}\" -s {device} uninstall {package_name}" \
        .format(adb_path=flask_config.adb_path, 
                device=device, 
                package_name=flask_config.package_name)
    ret_mes = subprocess.check_output(uninstall_format, shell=True)
    print(ret_mes.decode('utf-8'))

    install_format = "\"{adb_path}\" -s {device} install {apk_file_path}" \
        .format(adb_path=flask_config.adb_path, 
                device=device, 
                apk_file_path=flask_config.new_apk_file_path)
    ret_mes = subprocess.check_output(install_format, shell=True)
    print(ret_mes.decode('utf-8'))
    return jsonify()


@app.route('/api/save_modification', methods=['PUT'])
def save_modification():
    dict_modification = request.json
    temp_treedata = flask_config.treeData
    path_list = dict_modification['path'].split('\\')
    for path in path_list:
        for child in temp_treedata['children']:
            if child['name'] == path:
                temp_treedata = child
                break
    else:
        temp_treedata['modification_content'] = dict_modification['modification_content']
        return jsonify()


@app.route('/api/save_file', methods=['PUT'])
def save_file():
    dict_file = request.json
    temp_treedata = flask_config.treeData
    path_list = dict_file['path'].split('\\')
    for path in path_list:
        for child in temp_treedata['children']:
            if child['name'] == path:
                temp_treedata = child
                break
    else:
        with open(temp_treedata['path'], 'w') as f:
            f.write(dict_file['modification_content'])
        temp_treedata['content'] = dict_file['modification_content']
        temp_treedata['modification_content'] = dict_file['modification_content']
        
        return jsonify()


@app.route('/api/add_file', methods=['POST'])
def add_file():
    temp_treedata = flask_config.treeData
    path_list = request.form['dir_path'].split('\\')
    for path in path_list:
        for child in temp_treedata['children']:
            if child['name'] == path:
                temp_treedata = child
                break
    else:
        path_format = r"{dir_path}\{file_name}" \
            .format(dir_path=temp_treedata['path'],
                    file_name=request.form['file_name'])
        with open(path_format, 'w') as f:
            f.write(request.form['file_content'])
        dict_file = {
            'name': request.form['file_name'],
            'path': path_format,
            'type': 'file',
            'content': request.form['file_content'],
            'modification_content': request.form['file_content']
        }
        temp_treedata['children'].append(dict_file)
        return jsonify(dict_file)


@app.route('/api/remove_file', methods=['PUT'])
def remove_file():
    pre_temp_treedata = flask_config.treeData
    temp_treedata = flask_config.treeData
    path_list = request.json['path'].split('\\')
    for path in path_list:
        pre_temp_treedata = temp_treedata
        for child in temp_treedata['children']:
            if child['name'] == path:
                temp_treedata = child
                break
    else:
        path = request.json['path']
        delete_format = r"del /Q {path}".format(path=temp_treedata['path'])
        ret_mes = str(subprocess.check_output(delete_format, shell=True))
        pre_temp_treedata['children'].remove(temp_treedata)
        return jsonify()


@app.route('/api/upload_exists_keystore', methods=['POST'])
def upload_exists_keystore():
    flask_config.keystore_storepass = request.form['storepass']
    flask_config.keystore_alias = request.form['alias']
    f = request.files.get('file')
    f.save(flask_config.keystore_path)
    return jsonify()


@app.route('/api/new_keystore', methods=['POST'])
def new_keystore():
    dict_data = {key: value[0] for key, value in dict(request.form).items()}
    create_keystore(dict_data)
    flask_config.keystore_storepass = dict_data['storepass']
    flask_config.keystore_alias = dict_data['alias']
    return jsonify()


@app.route('/api/build_and_sign_apk', methods=['POST'])
def build_and_sign_apk():
    build_apk()
    sign_apk()
    return jsonify()


@app.route('/download/new_apk', methods=['GET'])
def download_new_apk():
    return send_file(flask_config.new_apk_file_path)
	

@app.route('/download/keystore', methods=['GET'])
def download_keystore():
    return send_file(flask_config.keystore_path)


@app.route('/api/get_log', methods=['GET'])
def get_log():
    file_content = ''
    with open(flask_config.log_file_path, 'r') as f:
        for line in f:
            file_content += line
    return jsonify(file_content)


@app.route('/api/start_get_log', methods=['GET'])
def start_get_log():
    p = Process(target=get_log_of_emulator('emulator-5554'))
    p.start()
    return jsonify()
    

#--------------------------------------------------------------
#   route
#--------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'GET':
        return render_template('upload.html')
    elif request.method == 'POST':
        f = request.files.get('file')
        flask_config.apk_name = (f.filename).split('.apk')[0]
        flask_config.apk_file_path = '{apk_file_dir}\{filename}' \
            .format(apk_file_dir=flask_config.apk_file_dir,
                    filename=secure_filename(f.filename))
        flask_config.unpack_dir_path = '{apk_file_dir}\{apk_name}' \
            .format(apk_file_dir=flask_config.apk_file_dir,
                    apk_name=flask_config.apk_name)
        flask_config.android_manifest_xml_path = '{unpack_dir_path}\AndroidManifest.xml' \
            .format(unpack_dir_path=flask_config.unpack_dir_path)
        f.save(flask_config.apk_file_path)
        unpack_apk()
        move_apk_to_dist_dir()
        read_package_name()
        flask_config.treeData = path_to_dict(flask_config.unpack_dir_path)
        return jsonify()


@app.route('/modification')
def modification():
    return render_template('modification.html')

@app.route('/keystore')
def keystore():
    return render_template('keystore.html')

@app.route('/build')
def build():
    return render_template('build.html')

@app.route('/emulator')
def emulator():
    return render_template('emulator.html')

@app.route('/install')
def install():
    return render_template('install.html')

@app.route('/log')
def log():
    return render_template('log.html')

@app.route('/test_index')
def test_index():
    return render_template('test_index.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)