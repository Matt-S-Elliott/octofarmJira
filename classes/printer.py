from pony.orm import *
from classes.enumDefinitions import *
import requests
import json
import time

db = Database()


class Printer(db.Entity):
    name = Required(str, unique=True)
    """Human friendly name for printer. Example: 'Prusa01' """
    printer_model = Required('PrinterModel')
    """Model of the printer."""
    ip = Required(str, unique=True)
    """IP address to send print files to and query print status from."""
    api_key = Required(str)
    """Required API key to communicate with printer."""
    stream_ip = Optional(str)
    """Optional IP address for a streaming camera."""
    material_type = Optional(str)
    material_color = Optional(str)
    material_density = Required(float)
    enabled = Required(bool)
    print_jobs = Set('PrintJob')
    """Used to relate print jobs to this printer. Not an actual field, just a Pony ORM thing"""

    def Get_Job_Url(self):
        return "http://" + self.ip + "/api/job"

    def Get_Upload_Url(self):
        return "http://" + self.ip + "/api/files/{}".format("local")

    def Get_Connection_Url(self):
        return "http://" + self.ip + "/api/connection"

    def Connect_Printer(self):
        connect = {'command': 'connect'}
        header = {'X-Api-Key': self.api_key}
        return requests.post(self.Get_Connection_Url(), json=connect, headers=header)

    def Disconnect_Printer(self):
        disconnect = {'command': 'disconnect'}
        header = {'X-Api-Key': self.api_key}
        return requests.post(self.Get_Connection_Url(), json=disconnect, headers=header)

    def Reconnect_Printer(self):
        self.Disconnect_Printer()
        self.Connect_Printer()

    def Get_Job(self):
        headers = {
            "Accept": "application/json",
            "Host": self.ip,
            "X-Api-Key": self.api_key
        }
        return requests.request(
            "GET",
            self.Get_Job_Url(),
            headers=headers
        )

    def Upload_Job(self, job):
        openFile = open(job.Get_File_Name(), 'rb')
        fle = {'file': openFile, 'filename': job.Get_Name()}
        payload = {'select': 'true', 'print': 'true'}
        header = {'X-Api-Key': self.api_key}
        return requests.post(self.Get_Upload_Url(), files=fle, data=payload, headers=header)
    
    def Upload_Test_Print(self):
        openFile = open('test_print.gcode', 'rb')
        fle = {'file': openFile, 'filename': 'test_print'}
        payload = {'select': 'true', 'print': 'true'}
        header = {'X-Api-Key': self.api_key}
        return requests.post(self.Get_Upload_Url(), files=fle, data=payload, headers=header)


    def Get_Printer_State(self, get_actual_volume=False):
        """Returns a tuple with the state as the first element. The second element is the actual weight used if the"""
        try:
            response = self.Get_Job()
            response = json.loads(response.text)
            state = response['state'].lower()
            # This only runs if prints were not sent through queue
            if state == 'operational' and response['progress']['completion'] == 100.0:
                if get_actual_volume:
                    return 'finished', response['job']['filament']['tool0']['volume']  # Also return actual volume printed if job is finished.
                else:
                    return 'finished'

            # This will never run; paused status is likely only sent by pausing through octoprint
            # elif state == 'paused' and response['progress']['completion'] == 100.0:
                # if get_actual_volume:
                #     return 'needs_clearing', response['job']['filament']['tool0']['volume']
                # else:
                #     return 'needs_clearing'

            # Very slow but speed isnt a priority here, will hold for other reasons
            with open("./jiradownloads/" + response['job']['file']['path']) as file:
                # won't work for google drive
                content = file.read()
                i = content.find("M0 D o n e ?")
                if response['progress']['filepos'] >= i - 10:
                    print("Found possibly complete PR: " + job.Get_Name())

            if get_actual_volume:
                return state, 0
            else:
                return state
        except Exception as e:
            print(self.name + " did not respond. Check connection and disable printer if needed.")
            if get_actual_volume:
                return 'offline', 0
            else:
                return 'offline'

    @staticmethod
    @db_session
    def Get_All():
        query_result = select(p for p in Printer)
        printers = []
        for p in query_result:
            printers.append(p)
        return printers

    @staticmethod
    @db_session
    def Get_All_Enabled():
        query_result = select(p for p in Printer if p.enabled is True)
        printers = []
        for p in query_result:
            printers.append(p)
        return printers

    @staticmethod
    @db_session
    def Get_All_By_Type(printer_model):
        query_result = select(p for p in Printer if p.printer_model == printer_model.id)
        printers = []
        for p in query_result:
            printers.append(p)
        return printers

    @staticmethod
    @db_session
    def Get_All_Printers_By_Count(enabled_only=True):
        """Counts any print that started on the printer, including failed jobs. Sorted with the smallest number of jobs first."""
        if enabled_only:
            query_result = left_join((p, count(pj)) for p in Printer if p.enabled for pj in p.print_jobs)[:]
        else:
            query_result = left_join((p, count(pj)) for p in Printer for pj in p.print_jobs)[:]
        printers = []
        for p in query_result:
            printers.append(p)
        printers.sort(key=lambda x: x[1])  # The second element of the tuple is the number of print jobs associated.
        return printers


    @staticmethod
    @db_session
    def Get_All_Printers_By_Count_And_Model(model, enabled_only=True):
        """Counts any print that started on the printer, including failed jobs. Sorted with the smallest number of jobs first."""
        if enabled_only:
            query_result = left_join((p, count(pj)) for p in Printer if p.enabled and p.printer_model.name == model.name for pj in p.print_jobs)[:]
        else:
            query_result = left_join((p, count(pj)) for p in Printer if p.printer_model.name == model.name for pj in p.print_jobs)[:]
        printers = []
        for p in query_result:
            printers.append(p)
        printers.sort(key=lambda x: x[1])  # The second element of the tuple is the number of print jobs associated.
        return printers

    @db_session
    def Get_Current_Job(self):
        for pj in self.print_jobs:
            if pj.print_status == PrintStatus.PRINTING.name:
                return pj

    @staticmethod
    def Map_Request(printer, form_data):
        """
        Maps request data to a printer object.
        """
        printer.name = form_data['name']
        printer.printer_model = int(form_data['printer_model'])
        printer.ip = form_data['ip']
        printer.api_key = form_data['api_key']
        printer.stream_ip = form_data['stream_ip']
        printer.material_type = form_data['material_type']
        printer.material_color = form_data['material_color']
        try:
            printer.material_density = float(form_data['material_density'])
        except:
            printer.material_density = None
        printer.enabled = form_data['enabled'] == 'true'

    @staticmethod
    @db_session
    def Add_From_Request(form_data):
        """
        Maps request data to a printer object.
        """
        name = form_data['name']
        printer_model = int(form_data['printer_model'])
        ip = form_data['ip']
        api_key = form_data['api_key']
        stream_ip = form_data['stream_ip']
        material_type = form_data['material_type']
        material_color = form_data['material_color']
        try:
            material_density = float(form_data['material_density'])
        except:
            material_density = None
        enabled = form_data['enabled'] == 'true'

        Printer(name=name, printer_model=printer_model, ip=ip, api_key=api_key, stream_ip=stream_ip, material_type=material_type, material_color=material_color, material_density=material_density, enabled=enabled)
