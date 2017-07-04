# -*- coding: utf-8 -*-
import codecs
import os
import subprocess
from subprocess import PIPE, STDOUT

from flask import Flask
from flask import jsonify, request
from flask import render_template
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
    apktool_format = "\"{apktool_path}\" b {apk_file_path}" \
        .format(apktool_path=flask_config.apktool_path, 
                apk_file_path=flask_config.apk_file_path)

    ret_mes = str(subprocess.check_output(apktool_format, shell=True))
    if 'ERROR' in ret_mes:
        print("Error", ret_mes)
        return False

    flask_config.new_apk_file_path = "{unpack_dir_path}\dist\{apk_name}" \
        .format(unpack_dir_path=flask_config.unpack_dir_path, 
                apk_name=flask_config.apk_name)

def create_sign(dict_sign_data):
    if dict_sign_data['creat_sign_flag']:
        print("Input keytool information:")
        keystore_path = input("keystore path: ")
        alias = input("alias: ")
        keypass = input("keypass: ")
        storepass = input("storepass: ")
        common_name = input("common name: ")
        organization_unit = input("organization unit: ")
        organization_name = input("organization name: ")
        locality_name = input("locality name: ")
        state_name = input("state name: ")
        country = input("country: ")
        
        keytool_format = \
            ("\"{java_path}\keytool\" -genkey -v -keyalg DSA -keysize 1024 -sigalg SHA1withDSA -validity 20000 " + \
            "-keystore {keystore_path} -alias {alias} -keypass {keypass} -storepass {storepass}") \
            .format(java_path=flask_config.java_path,
                    keystore_path=flask_config.keystore_path,
                    alias=dict_sign_data['alias'],
                    keypass=dict_sign_data['keypass'],
                    storepass=dict_sign_data['storepass'])

        keytool_sign_info_format = \
            "{common_name}\n{organization_unit}\n{organization_name}\n{locality_name}\n{state_name}\n{country}\ny\n" \
            .format(common_name=dict_sign_data['common_name'],
                    organization_unit=dict_sign_data['organization_unit'],
                    organization_name=dict_sign_data['organization_name'],
                    locality_name=dict_sign_data['locality_name'],
                    state_name=dict_sign_data['state_name'],
                    country=dict_sign_data['country'])
        
        p = subprocess.Popen(keytool_format, stdout=PIPE, stdin=PIPE, stderr=STDOUT)
        
        out = p.communicate(input=keytool_sign_info_format.encode())[0]
        if 'Exception' in str(out):
            print("Exception", str(out))
            return False
        else:
            print("create sign success!")


def sign_apk(dict_sign_data):
    jarsigner_format = \
        ("\"{java_path}\jarsigner\" -tsa http://timestamp.digicert.com -verbose -sigalg SHA1withDSA -digestalg SHA1 " + \
        "-keystore {keystore_path} -storepass {storepass} \"{apk_file_path}\" {alias}") \
        .format(java_path=flask_config.java_path,
                keystore_path=flask_config.keystore_path,
                storepass=flask_config.sign_storepass,
                apk_file_path=flask_config.new_apk_file_path,
                alias=flask_config.sign_alias)
                
    p = subprocess.Popen(jarsigner_format, stdout=PIPE, stdin=PIPE, stderr=STDOUT)
    out = p.communicate()[0]
    if 'jar signed' in str(out):
        print("Success!")
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
        
    z7za_path_format = "\"{z7za_path}\" e -y {apk_file_path} classes.dex -o{unpack_dir_path}" \
        .format(z7za_path=flask_config.z7za_path, 
                apk_file_path=flask_config.apk_file_path,
                unpack_dir_path=flask_config.unpack_dir_path)

    ret_mes = str(subprocess.check_output(z7za_path_format, shell=True))
    if 'Error' in str(ret_mes) or 'ERROR' in str(ret_mes):
        print("Error", str(ret_mes))
        return False
    else:
        print("extract classes.dex success!")
        
    dex2jar_path_format = "\"{dex2jar_path}\" -f {unpack_dir_path}\classes.dex -o {unpack_dir_path}\classes.jar" \
        .format(dex2jar_path=flask_config.dex2jar_path,
                unpack_dir_path=flask_config.unpack_dir_path)
    ret_mes = str(subprocess.check_output(dex2jar_path_format, shell=True))
    return True


#--------------------------------------------------------------
#   api
#--------------------------------------------------------------
@app.route('/api/treeData', methods=['GET'])
def treeData():
    return jsonify(path_to_dict(flask_config.apk_file_dir))


@app.route('/api/getEmulatorDevices', methods=['GET'])
def getEmulatorDevices():
    emulator_list_format = "\"{emulator_path}\" -list-avds" \
        .format(emulator_path=flask_config.emulator_path)

    ret_mes = subprocess.check_output(emulator_list_format, shell=True)
    device_list = [device.strip() for device in ret_mes.decode('utf-8').split('\n') if device]
    flask_config.devices_list = []
    return_devices_list = []
    for idx, device in enumerate(device_list):
        flask_config.devices_list.append(device)
        return_devices_list.append({
            "idx": idx,
            "device": device})
        print(idx, ':', device)
    return jsonify(return_devices_list)


@app.route('/api/startEmulatorDevices', methods=['POST'])
def startEmulatorDevices():
    device = str(request.data,'utf-8')
    open_emulator_format = "\"{emulator_path}\" -avd {device} -netdelay none -netspeed full" \
	    .format(emulator_path=flask_config.emulator_path, 
                device=device)
    ret_mes = subprocess.check_output(open_emulator_format, shell=True)
    return jsonify()


@app.route('/api/getStartEmulatorDevices', methods=['GET'])
def getStartEmulatorDevices():
    adb_list_format = "\"{adb_path}\" devices" \
        .format(adb_path=flask_config.adb_path)

    ret_mes = subprocess.check_output(adb_list_format, shell=True)

    device_list = [device.split('\t')[0].strip() for device in ret_mes.decode('utf-8').split('\n') \
        if device.strip() and len(device.split('\t')) == 2 and 'device' in device.split('\t')[-1]]
    flask_config.start_devices_list = []
    return_start_devices_list = []
    for idx, device in enumerate(device_list):
        flask_config.start_devices_list.append(device)
        return_start_devices_list.append({
            'idx': idx,
            'device': device
        })
        print(idx, ':', device)
    return jsonify(return_start_devices_list)


@app.route('/api/reinstallAPK', methods=['PUT'])
def reinstallAPK():
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


@app.route('/api/save_file', methods=['PUT'])
def save_file():
    dict_file = request.get_json()
    with open(dict_file['path'], 'w') as f:
        f.write(dict_file['modification_content'])
    return jsonify()


@app.route('/api/upload_exists_sign', methods=['POST'])
def upload_exists_sign():
    flask_config.sign_storepass = request.form['storepass']
    flask_config.sign_alias = request.form['alias']
    f = request.files.get('file')
    print(flask_config.sign_storepass)
    print(flask_config.sign_alias)
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
        f.save(flask_config.apk_file_path)
        unpack_apk()


@app.route('/modification')
def modification():
    return render_template('modification.html')

@app.route('/sign')
def sign():
    return render_template('sign.html')

@app.route('/emulator')
def emulator():
    return render_template('emulator.html')

@app.route('/reinstall')
def reinstall():
    return render_template('reinstall.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)