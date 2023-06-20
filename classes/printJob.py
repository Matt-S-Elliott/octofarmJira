from classes.message import *
import datetime

class PrintJob(db.Entity):
    printer_model = Optional('PrinterModel')
    printed_on = Optional(Printer)
    """Printer this job was processed on."""
    permission_code = Optional('PermissionCode')
    job_id = Required(int, unique=True)
    """ID from the job submission system. We use Jira. This will be the unique ID generated by jira. Only digits in our case."""
    job_name = Optional(str, unique=True)
    """Optional custom job name from the submission system. We use PR-#### formatted names."""
    user = Required('User')
    job_created_date = Optional(datetime.datetime)
    """Time job was added to DB"""
    job_submitted_date = Optional(datetime.datetime)
    """Time job was submitted in jira"""
    print_started_date = Optional(datetime.datetime)
    print_finished_date = Optional(datetime.datetime)
    payment_link_generated_date = Optional(datetime.datetime)
    paid_date = Optional(datetime.datetime)
    payment_link = Optional(str)
    weight = Optional(float)
    """In grams"""
    cost = Optional(float)
    print_time = Optional(int)
    """In seconds"""
    url_type = Optional(str)
    """UrlTypes Enum"""
    gcode_url = Optional(str)
    print_status = Required(str)
    """PrintStatus Enum"""
    payment_status = Optional(str)
    """PaymentStatus Enum"""
    failure_message = Optional(Message)
    """MessageNames Enum"""

    def Get_Name(self, job_name_only=False):
        if self.job_name and job_name_only:
            name = self.job_name
        elif self.job_name:
            name = self.job_name + '_' + str(self.job_id)
        else:
            name = str(self.job_id)
        return name

    def Get_File_Name(self):
        name = self.Get_Name()
        if self.url_type == UrlTypes.JIRA_ATTACHMENT.name:
            return "jiradownloads/" + name + ".gcode"
        elif self.url_type == UrlTypes.GOOGLE_DRIVE.name:
            return "drivedownloads/" + name + ".gcode"

    @staticmethod
    @db_session
    def Get_All_By_Status(print_status: PrintStatus, serialize=False):
        query_result = select(pj for pj in PrintJob if pj.print_status == print_status.name)
        print_jobs = []
        for p in query_result:
            print_jobs.append(p)
        if serialize:
            return PrintJob.Serialize_Jobs_For_Queue(print_jobs)
        return print_jobs

    @staticmethod
    @db_session
    def Get_Print_Queue_And_Printing():
        query_result = select(pj for pj in PrintJob if pj.print_status == PrintStatus.PRINTING.name or pj.print_status == PrintStatus.IN_QUEUE.name)
        print_jobs = []
        for p in query_result:
            print_jobs.append(p)
        return PrintJob.Serialize_Jobs_For_Queue(print_jobs)

    @staticmethod
    @db_session
    def Get_Jobs_For_Permission_Code(permission_code):
        print_jobs = []
        with db_session:
            query_result = select(pj for pj in PrintJob if pj.print_status == PrintStatus.FINISHED.name and pj.permission_code.id == permission_code and pj.payment_link_generated_date is None)
            for p in query_result:
                print_jobs.append(p)
        return print_jobs

    @staticmethod
    @db_session
    def Get_All(serialize=False):
        query_result = select(pj for pj in PrintJob)
        print_jobs = []
        for p in query_result:
            print_jobs.append(p)
        print_jobs.sort(key=lambda x: x.id)
        if serialize:
            return PrintJob.Serialize_Jobs_For_Job_List(print_jobs)
        return print_jobs
        
    @staticmethod
    @db_session
    def Get_All_Print_Jobs_Screen(job_count):
        query_result = select(pj for pj in PrintJob)
        print_jobs = []
        for p in query_result:
            print_jobs.append(p)
        print_jobs.sort(key=lambda x: x.id, reverse=True)
        if (job_count > len(print_jobs) - 1):
            job_count = len(print_jobs)
        
        return PrintJob.Serialize_Jobs_For_Job_List(print_jobs[0:job_count])
        
    @staticmethod
    def Serialize_Jobs_For_Queue(jobs):
        result = []
        for j in jobs:
            result.append(j.To_Dict_For_Queue())
        return json.dumps(result)

    @staticmethod
    def Serialize_Jobs_For_Job_List(jobs):
        result = []
        for j in jobs:
            result.append(j.To_Dict_For_Job_List())
        return json.dumps(result)

    def Generate_Start_Message(self):
        startTime = datetime.datetime.now().strftime("%I:%M" '%p')
        if startTime[0] == '0':
            startTime = startTime[1:]
        text = "Print was started at: " + startTime + "\n"
        text += "Estimated print weight: " + str(self.weight) + "g\n"
        text += "Estimated print time: " + str(datetime.timedelta(seconds=self.print_time)) + "\n"
        text += "Estimated print cost: " + "${:,.2f}".format(self.cost)
        return text

    @db_session
    def Mark_Job_Finished(self, actual_print_volume = None):
        if (actual_print_volume):
            self.weight = round(self.printed_on.material_density * actual_print_volume, 2)
        if (self.permission_code):
            self.cost = round(self.weight * 0.05, 2)
        else:
            self.cost = round(self.weight * 0.05 * 1.0775, 2)
        self.print_status = PrintStatus.FINISHED.name
        self.print_finished_date = datetime.datetime.now()
        self.payment_status = PaymentStatus.NEEDS_PAYMENT_LINK.name

    @db_session
    def Generate_Finish_Message(self):
        finishTime = datetime.datetime.now().strftime("%I:%M" '%p')
        if finishTime[0] == '0':
            finishTime = finishTime[1:]
        text = "{color:#00875A}Print completed successfully!{color}\n\n"
        text += "Print harvested at: " + finishTime + "\n"
        text += "Actual filament used: " + str(self.weight) + "g\n"
        text += "Actual print cost: " + "${:,.2f}".format(self.cost) + "\n\n"

        if self.permission_code:
            message = Message.get(name=MessageNames.FINISH_TEXT_TAX_EXEMPT.name)
            if message:
                text += message.text
        else:
            message = Message.get(name=MessageNames.FINISH_TEXT_WITH_TAX.name)
            if message:
                text += message.text

        return text

    def To_Dict_For_Queue(self):
        """Same as To_Dict_For_Job_List except with fewer fields."""
        result = {
            'job_id': self.job_id,
            'job_name': self.job_name,
            'print_status': self.print_status,
            'printed_on': self.printed_on.name if self.printed_on else '',
            'job_submitted_date': self.job_submitted_date.strftime("%m/%d/%Y, %H:%M:%S"),
            'printer_model': self.printer_model.name,
            'printer_model_id': self.printer_model.id,
            'auto_start': self.printer_model.auto_start_prints,
            'print_time': self.print_time
        }
        return result

    def To_Dict_For_Job_List(self):
        """Same as To_Dict_For_Queue except with more fields."""
        result = {
            'job_id': self.job_id,
            'job_name': self.job_name,
            'print_status': self.print_status,
            'printed_on': self.printed_on.name if self.printed_on else '',
            'job_submitted_date': self.job_submitted_date.strftime("%m/%d/%Y, %H:%M:%S") if self.job_submitted_date else '',
            'print_started_date': self.print_started_date.strftime("%m/%d/%Y, %H:%M:%S") if self.print_started_date else '',
            'print_finished_date': self.print_finished_date.strftime("%m/%d/%Y, %H:%M:%S") if self.print_finished_date else '',
            'printer_model': self.printer_model.name if self.printer_model else '',
            'printer_model_id':self.printer_model.id if self.printer_model else '',
            'permission_code': self.permission_code.name if self.permission_code else '',
            'weight': self.weight,
            'cost': self.cost,
            'print_time': self.print_time,
            'payment_status': self.payment_status,
            'payment_link': self.payment_link,
            'payment_link_generated_date': self.payment_link_generated_date,
            'paid_date': self.paid_date,
        }
        return result
