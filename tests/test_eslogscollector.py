from cloudshell.api.cloudshell_api import CloudShellAPISession, InputNameValue
import base64

server = raw_input("Quali Server Address:")
username = raw_input("Quali Username:")
password = raw_input("Quali Password:")
domain = raw_input("Quali Domain:")

res_id = raw_input("Sandbox ID:")
log_collector_name = raw_input("LogCollector Resource Name:")
email = raw_input("Email Address:")
api = CloudShellAPISession(server, username, password, domain)
res_input = InputNameValue(Name="reservation_id", Value=res_id)
email_input = InputNameValue(Name="email_to", Value=email)
try:
    api.ExecuteCommand(reservationId=res_id, targetName=log_collector_name, targetType="Resource", commandName="get_logs_attach", commandInputs=[res_input])
except Exception, e:
    print "{}".format(e)

try:
    api.ExecuteCommand(reservationId=res_id, targetName=log_collector_name, targetType="Resource", commandName="get_logs_email", commandInputs=[res_input, email_input])
except Exception, e:
    print "{}".format(e)

try:
    output = api.ExecuteCommand(reservationId=res_id, targetName=log_collector_name, targetType="Resource", commandName="get_logs_base64", commandInputs=[res_input]).Output
    with open("C:\\Temp\\TestZip.zip", "wb") as fl:
        fl.write(base64.b64decode(output))
except Exception, e:
    print "{}".format(e)
