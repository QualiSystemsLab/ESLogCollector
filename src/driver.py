from cloudshell.shell.core.driver_context import AutoLoadDetails, CancellationContext
from cloudshell.shell.core.resource_driver_interface import ResourceDriverInterface
from cloudshell.shell.core.driver_context import InitCommandContext, ResourceCommandContext
from cloudshell.api.cloudshell_api import CloudShellAPISession
import paramiko
import scp
import tempfile
import shutil
import winrm
import zipfile
import requests
import socket
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication
import os


class SMTP:
    def __init__(self):
        socket.setdefaulttimeout(60)

    def _email(self, smtp_server, smtp_port, tls, smtp_username, smtp_password, from_name, to_address, msg):
        smtp = smtplib.SMTP(host=smtp_server, port=int(smtp_port))
        smtp.ehlo()
        if tls:
            smtp.starttls()
            smtp.ehlo()
        if smtp_username:
            smtp.esmtp_features['auth'] = 'LOGIN PLAIN'
            smtp.login(user=smtp_username, password=smtp_password)
        smtp.sendmail(from_addr=from_name, to_addrs=to_address, msg=msg.as_string())
        smtp.close()

    def send_email(self, smtp_username, smtp_password, smtp_server, smtp_port, from_name, to_address, subject, tls,
                    message, is_html, picture, attachment):
        msg = MIMEMultipart('alternative')
        msg['From'] = from_name
        msg['To'] = to_address
        msg['Subject'] = subject
        if is_html:
            mess = MIMEText(message, 'html')
        else:
            mess = MIMEText(message, 'plain')
        msg.attach(mess)
        if picture:
            img = file(picture, "rb").read()
            img = MIMEImage(img, 'html')
            aa = '<img src="data:image/jpeg;base64,{}">'.format(img._payload)
            img = MIMEText(aa, 'html')
            msg.attach(img)
        if attachment:
            attach = file(attachment, "rb").read()
            att = MIMEApplication(attach, Name="{}".format(attachment.split("\\")[-1]))
            att['Content-Disposition'] = 'attachment; filename="{}"'.format(attachment.split("\\")[-1])
            msg.attach(att)

        try:
            self._email(smtp_server, smtp_port, tls, smtp_username, smtp_password, from_name, to_address, msg)
        except Exception, _exp:
            raise Exception(str(_exp))


class LinuxConnection:
    def __init__(self):
        self.ssh = None
        self.chan = None
        self.scp = None

    def connect(self, ip, user, password, timeout=120):
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(ip, 22, user, password, timeout=timeout)
            ssh.keep_this = True
            self.ssh = ssh
            self.scp = scp.SCPClient(self.ssh.get_transport())
            self.chan = self.ssh.invoke_shell()
            self.chan.send("\n")
            self.chan.recv(1024)
        except Exception, e:
            raise

    def run_command(self, command, prompt):
        self.chan.send(command + "\n")
        output = ""
        while output.count(prompt) < 3:
            output += self.chan.recv(1024)
        return output

    def download_file(self, path, local_path):
        self.scp.get(path, recursive=True, local_path=local_path)


class WindowsConnection:
    def __init__(self):
        self.winrm = ""

    def connect(self, ip, user, password, timeout=120):
        try:
            win_rm = winrm.Session(ip, auth=(user, password), transport="ntlm", server_cert_validation='ignore',
                                   operation_timeout_sec=timeout)
            win_rm.protocol.transport.endpoint = win_rm.protocol.transport.endpoint.replace("http://", "https://").replace(":5985", ":5986")
            self.winrm = win_rm
        except Exception, e:
            raise

    def run_command(self, command):
        output = self.winrm.run_cmd(command)
        return output.status_code, output.std_out, output.std_err

    def download_file(self, path, local_path):
        _, files, _ = self.run_command("dir {} /s /b".format(path))
        for line in files.splitlines():
            if not line:
                continue
            status, content, err = self.run_command('type "{}"'.format(line))

            if status != 0:
                continue
            file_loc = line.lower().replace(path.lower(), "")
            new_file_path = local_path + file_loc
            if not os.path.exists(os.path.dirname(new_file_path)):
                os.makedirs(os.path.dirname(new_file_path))
            open(new_file_path, "w").write(content)


class LogCollector():
    def __init__(self, context, reservation_id=None):
        """
        :param ResourceCommandContext context:
        """
        self.api = CloudShellAPISession(context.connectivity.server_address,
                                        token_id=context.connectivity.admin_auth_token, domain='Global')
        self.model_name = context.resource.model
        self.windows_user = context.resource.attributes["{}.Windows User".format(self.model_name)]
        self.windows_password = context.resource.attributes["{}.Windows Password".format(self.model_name)]
        try:
            self.windows_password = self.api.DecryptPassword(self.windows_password).Value
        except:
            pass
        self.windows_es = [x.lstrip().strip() for x in context.resource.attributes["{}.Windows ES List".format(self.model_name)].split(",")]
        self.linux_user = context.resource.attributes["{}.Linux User".format(self.model_name)]
        self.linux_password = context.resource.attributes["{}.Linux Password".format(self.model_name)]
        try:
            self.linux_password = self.api.DecryptPassword(self.linux_password).Value
        except:
            pass
        self.linux_es = [x.lstrip().strip() for x in context.resource.attributes["{}.Linux ES List".format(self.model_name)].split(",")]
        self.res_id = reservation_id if reservation_id else context.reservation.reservation_id
        self.scp_client = LinuxConnection()
        self.winrm = WindowsConnection()
        self.temp_folder = ""
        self.zip_file_name = ""
        self.linux_log_location = context.resource.attributes["{}.Linux Log Location".format(self.model_name)]
        self.windows_log_location = context.resource.attributes["{}.Windows Log Location".format(self.model_name)]
        self.smtp_server = context.resource.attributes["{}.SMTP Server".format(self.model_name)]
        self.smtp_port = context.resource.attributes["{}.SMTP Port".format(self.model_name)]
        self.smtp_tls = context.resource.attributes["{}.SMTP TLS".format(self.model_name)]
        self.smtp_username = context.resource.attributes["{}.SMTP Username".format(self.model_name)]
        self.smtp_password = context.resource.attributes["{}.SMTP Password".format(self.model_name)]
        try:
            self.smtp_password = self.api.DecryptPassword(self.smtp_password).Value
        except:
            pass
        self.smtp_from = context.resource.attributes["{}.SMTP From Name".format(self.model_name)]
        self.context = context
        self._preapre_env()

    def _preapre_env(self):
        self.temp_folder = tempfile.mkdtemp(self.res_id)

    def clean_env(self):
        shutil.rmtree(self.temp_folder)

    def get_linux_logs(self):
        for linux_es in self.linux_es:
            self.scp_client.connect(linux_es, self.linux_user, self.linux_password, 5)
            output = self.scp_client.run_command("ls {}".format(self.linux_log_location), "$")
            if self.res_id in output:
                print "Found res id folder in es {}".format(linux_es)
                self.scp_client.download_file("{}/{}/lib/".format(self.linux_log_location, self.res_id),
                                              self.temp_folder + "/{}".format(linux_es))
            else:
                print "unable to find {} in es {}".format(self.res_id, linux_es)
                # raise Exception(output)

    def get_windows_logs(self):
        for windows_es in self.windows_es:
            self.winrm.connect(windows_es, self.windows_user, self.windows_password, 10)
            status, output, err = self.winrm.run_command("dir {}".format(self.windows_log_location))
            if self.res_id in output:
                print "Found res id folder in es {}".format(windows_es)
                self.winrm.download_file("{}\\{}".format(self.windows_log_location, self.res_id),
                                         self.temp_folder + "/{}".format(windows_es))

            else:
                print "unable to find {} in es {}".format(self.res_id, windows_es)
                # raise Exception(output)

    def zip_logs(self):
        self.zip_file_name = "{}\\{}-LOGS.zip".format(self.temp_folder, self.res_id)
        self.zip_file = zipfile.ZipFile(self.zip_file_name, "w", zipfile.ZIP_DEFLATED)
        for root, dirs, files in os.walk(self.temp_folder):
            for fil in files:
                if fil == self.zip_file_name.split("\\")[-1]:
                    continue
                self.zip_file.write(os.path.join(root, fil), os.path.join(root, fil).split(self.res_id)[-1])
        self.zip_file.close()

    def upload_to_cs(self):

        api_base_url = "http://{}:9000/Api".format(self.context.connectivity.server_address)
        login_result = requests.put(api_base_url + "/Auth/Login", {"token": self.context.connectivity.admin_auth_token,
                                                                   "domain": "Global"})
        authcode = "Basic " + login_result._content[1:-1]

        attached_file = open(self.zip_file_name, "rb")
        attach_file_result = requests.post(api_base_url + "/Package/AttachFileToReservation",
                                           headers={"Authorization": authcode},
                                           data={"reservationId": self.res_id,
                                                 "saveFileAs": self.zip_file_name.split("\\")[-1], "overwriteIfExists": "True"},
                                           files={'QualiPackage': attached_file})

    def email_logs(self, to):
        email = SMTP()
        email.send_email(self.smtp_username, self.smtp_password, self.smtp_server, self.smtp_port,
                         self.smtp_from, to, "Logs for Sandbox: {}".format(self.res_id),
                         self.smtp_tls, "Logs", False, False, self.zip_file_name)

    def get_byte_logs(self):
        import base64
        with open(self.zip_file_name, "rb") as fl:
            out = base64.b64encode(fl.read())
        return out


class EslogscollectorDriver (ResourceDriverInterface):

    def __init__(self):
        """
        ctor must be without arguments, it is created with reflection at run time
        """
        pass

    def initialize(self, context):
        """
        Initialize the driver session, this function is called everytime a new instance of the driver is created
        This is a good place to load and cache the driver configuration, initiate sessions etc.
        :param InitCommandContext context: the context the command runs on
        """
        pass

    def cleanup(self):
        """
        Destroy the driver session, this function is called everytime a driver instance is destroyed
        This is a good place to close any open sessions, finish writing to log files
        """
        pass

    # <editor-fold desc="Discovery">

    def get_inventory(self, context):
        """
        Discovers the resource structure and attributes.
        :param AutoLoadCommandContext context: the context the command runs on
        :return Attribute and sub-resource information for the Shell resource you can return an AutoLoadDetails object
        :rtype: AutoLoadDetails
        """
        # See below some example code demonstrating how to return the resource structure and attributes
        # In real life, this code will be preceded by SNMP/other calls to the resource details and will not be static
        # run 'shellfoundry generate' in order to create classes that represent your data model

        '''
        resource = Eslogscollector.create_from_context(context)
        resource.vendor = 'specify the shell vendor'
        resource.model = 'specify the shell model'

        port1 = ResourcePort('Port 1')
        port1.ipv4_address = '192.168.10.7'
        resource.add_sub_resource('1', port1)

        return resource.create_autoload_details()
        '''
        return AutoLoadDetails([], [])

    # </editor-fold>

    # <editor-fold desc="Orchestration Save and Restore Standard">
    def orchestration_save(self, context, cancellation_context, mode, custom_params):
      """
      Saves the Shell state and returns a description of the saved artifacts and information
      This command is intended for API use only by sandbox orchestration scripts to implement
      a save and restore workflow
      :param ResourceCommandContext context: the context object containing resource and reservation info
      :param CancellationContext cancellation_context: Object to signal a request for cancellation. Must be enabled in drivermetadata.xml as well
      :param str mode: Snapshot save mode, can be one of two values 'shallow' (default) or 'deep'
      :param str custom_params: Set of custom parameters for the save operation
      :return: SavedResults serialized as JSON
      :rtype: OrchestrationSaveResult
      """

      # See below an example implementation, here we use jsonpickle for serialization,
      # to use this sample, you'll need to add jsonpickle to your requirements.txt file
      # The JSON schema is defined at:
      # https://github.com/QualiSystems/sandbox_orchestration_standard/blob/master/save%20%26%20restore/saved_artifact_info.schema.json
      # You can find more information and examples examples in the spec document at
      # https://github.com/QualiSystems/sandbox_orchestration_standard/blob/master/save%20%26%20restore/save%20%26%20restore%20standard.md
      '''
            # By convention, all dates should be UTC
            created_date = datetime.datetime.utcnow()

            # This can be any unique identifier which can later be used to retrieve the artifact
            # such as filepath etc.

            # By convention, all dates should be UTC
            created_date = datetime.datetime.utcnow()

            # This can be any unique identifier which can later be used to retrieve the artifact
            # such as filepath etc.
            identifier = created_date.strftime('%y_%m_%d %H_%M_%S_%f')

            orchestration_saved_artifact = OrchestrationSavedArtifact('REPLACE_WITH_ARTIFACT_TYPE', identifier)

            saved_artifacts_info = OrchestrationSavedArtifactInfo(
                resource_name="some_resource",
                created_date=created_date,
                restore_rules=OrchestrationRestoreRules(requires_same_resource=True),
                saved_artifact=orchestration_saved_artifact)

            return OrchestrationSaveResult(saved_artifacts_info)
      '''
      pass

    def orchestration_restore(self, context, cancellation_context, saved_artifact_info, custom_params):
        """
        Restores a saved artifact previously saved by this Shell driver using the orchestration_save function
        :param ResourceCommandContext context: The context object for the command with resource and reservation info
        :param CancellationContext cancellation_context: Object to signal a request for cancellation. Must be enabled in drivermetadata.xml as well
        :param str saved_artifact_info: A JSON string representing the state to restore including saved artifacts and info
        :param str custom_params: Set of custom parameters for the restore operation
        :return: None
        """
        '''
        # The saved_details JSON will be defined according to the JSON Schema and is the same object returned via the
        # orchestration save function.
        # Example input:
        # {
        #     "saved_artifact": {
        #      "artifact_type": "REPLACE_WITH_ARTIFACT_TYPE",
        #      "identifier": "16_08_09 11_21_35_657000"
        #     },
        #     "resource_name": "some_resource",
        #     "restore_rules": {
        #      "requires_same_resource": true
        #     },
        #     "created_date": "2016-08-09T11:21:35.657000"
        #    }

        # The example code below just parses and prints the saved artifact identifier
        saved_details_object = json.loads(saved_details)
        return saved_details_object[u'saved_artifact'][u'identifier']
        '''
        pass

    # </editor-fold>
    def get_logs_attach(self, context, reservation_id=None):
        """
        :param ResourceCommandContext context:
        """

        logs = LogCollector(context, reservation_id)
        try:
            logs.get_linux_logs()
            logs.get_windows_logs()
            logs.zip_logs()
            logs.upload_to_cs()
        except Exception, e:
            raise
        finally:
            logs.clean_env()

    def get_logs_email(self, context, email_to, reservation_id=None):
        """
        :param ResourceCommandContext context:
        """
        logs = LogCollector(context, reservation_id)
        try:

            logs.get_linux_logs()
            logs.get_windows_logs()
            logs.zip_logs()
            logs.email_logs(email_to)
        except Exception, e:
            raise
        finally:
            logs.clean_env()

    def get_logs_base64(self, context, reservation_id=None):
        """
        :param ResourceCommandContext context:
        """

        logs = LogCollector(context, reservation_id)
        try:
            logs.get_linux_logs()
            logs.get_windows_logs()
            logs.zip_logs()
            output = logs.get_byte_logs()
        except Exception, e:
            raise
        finally:
            logs.clean_env()
        return output

