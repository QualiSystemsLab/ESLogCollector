1) Install Shell - 'Shellfoundry install'
2) From the Inventory view, Create new resource from type "Eslogcollector" - Name & Address are irrelevant 
3) Fill in the attribute values

Example can be found under the tests folder

```python

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
    
```

