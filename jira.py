import datetime

from requests.auth import HTTPBasicAuth
import yaml
from classes.permissionCode import *
from classes.user import *
import os
import time
from classes.enumDefinitions import *

# load all of our config files
with open("config_files/config.yml", "r") as yamlFile:
    config = yaml.load(yamlFile, Loader=yaml.FullLoader)

# jira authentication information that gets pulled in from the config ###
auth = HTTPBasicAuth(config['jira_user'], config['jira_password'])


def get_issues():
    """
    Get the list of issues in the jira project
    """
    url = config['base_url'] + "/rest/api/2/" + config['search_url']
    headers = {
        "Accept": "application/json"
    }
    try:
        response = requests.request(
            "GET",
            url,
            headers=headers,
            auth=auth
        )

        # parse all open projects:
        openIssues = json.loads(json.dumps(json.loads(response.text), sort_keys=True, indent=4, separators=(",", ": ")))
        issues = []
        for issue in openIssues['issues']:
            url = issue['self']
            headers = {
                "Accept": "application/json"
            }
            response = requests.request(
                "GET",
                url,
                headers=headers,
                auth=auth
            )
            if response.ok:
                issues.append(response)
            else:
                print("Bad response from Jira on issue:", issue.split('/')[-1])
    except requests.exceptions.Timeout as errt:
        print("Timeout Error while getting issues.")
        return [];
    return issues


def parse_permission_code(description):
    start = "*Funding Code* \\\\"
    end = "\n\n\n\n*Description of print*"
    code_string = description[description.find(start) + len(start):description.rfind(end)]
    if code_string:
        code = PermissionCode.get(code=code_string)
        if code:
            return code.id
        else:
            return 1  # Permission code ID 1 is an invalid code.
    return None


def parse_gcode_url(issue):
    attachments = issue['fields']['attachment']
    if attachments:
        return attachments[0]['content'], UrlTypes.JIRA_ATTACHMENT

    description = issue['fields']['description']
    split = description.split('\\\\')
    for s in split:
        if s.startswith('https'):
            url = s[:s.rfind('\n\n')]
            if "drive.google.com" in url:
                split = url.split('/')
                return split[5], UrlTypes.GOOGLE_DRIVE
            else:
                return url, UrlTypes.UNKNOWN

    return '', UrlTypes.UNKNOWN


@db_session
def get_new_print_jobs():
    # Get the IDs of issues that are new and have not been processed to ensure we don't add duplicates
    print("Checking Jira for new issues...")
    existing_issues = PrintJob.Get_All()
    existing_ids = []
    if existing_issues:
        for issue in existing_issues:
            existing_ids.append(issue.job_id)

    new_issues = get_issues()
    print(str(len(new_issues)) + " new issues found.")

    new_print_jobs = []
    for issue in new_issues:
        parsed_issue = json.loads(issue.text)
        job_id = parsed_issue['id']
        if int(job_id) in existing_ids:
            continue
        job_name = parsed_issue['key']

        user_id = parsed_issue['fields']['customfield_11202'] # Normal users will use this format
        if (not user_id): # Jira users will use this format
            user_id = parsed_issue['fields']['reporter']['name'] # Normal users will use this format
        user_name = parsed_issue['fields']['customfield_11201']
        if (not user_name): # Jira users will use this format
            user_name = parsed_issue['fields']['reporter']['displayName']
        user = User.Get_Or_Create(user_id, user_name)
        permission_code_id = parse_permission_code(parsed_issue['fields']['description'])
        gcode_url, url_type = parse_gcode_url(parsed_issue)
        job_submitted_date_text = parsed_issue['fields']['created'].split('.')[0]  # Remove garbage after the decimal. They give a weird date format, but it is local time.
        job_submitted_date = datetime.datetime.fromisoformat(job_submitted_date_text)

        new_print_jobs.append(PrintJob(job_submitted_date=job_submitted_date, job_created_date=datetime.datetime.now(), job_id=job_id, job_name=job_name, print_status=PrintStatus.NEW.name, user=user.id, permission_code=permission_code_id, gcode_url=gcode_url, url_type=url_type.name))
    commit()
    return new_print_jobs


def download(job):
    """
    Downloads the files that getGcode wants
    """

    headers = {
        "Accept": "application/json"
    }

    try:
        response = requests.request(
            "GET",
            job.gcode_url,
            headers=headers,
            auth=auth
        )
    except Exception as e:
        print("Ticket " + job.Get_Name() + " error while downloading gcode from jira.")
        print(e)
        return "ERROR"

    if response.ok:
        return response.text
    else:
        print("Ticket " + job.Get_Name() + ": " + str(response.status_code) + " while downloading gcode from jira.")
        return "ERROR"


def send_fail_message(job, message_text):
    """
    Comments on a ticket with the provided message and stops the progress on the ticket.
    """
    commentStatus(job, message_text)
    changeStatus(job, JiraTransitionCodes.START_PROGRESS)
    changeStatus(job, JiraTransitionCodes.READY_FOR_REVIEW)
    changeStatus(job, JiraTransitionCodes.REJECT)


def send_print_started(job):
    """
    Comments on a ticket with the provided message and stops the progress on the ticket.
    """
    return commentStatus(job, job.Generate_Start_Message())


def send_print_queued(job):
    changeStatus(job, JiraTransitionCodes.START_PROGRESS)


def send_print_cancelled(job):
    if job.print_status == PrintStatus.NEW.name:
        changeStatus(job, JiraTransitionCodes.START_PROGRESS)
        changeStatus(job, JiraTransitionCodes.READY_FOR_REVIEW)
        changeStatus(job, JiraTransitionCodes.REJECT)
    if job.print_status == PrintStatus.IN_QUEUE.name or job.print_status == PrintStatus.PRINTING.name:
        changeStatus(job, JiraTransitionCodes.READY_FOR_REVIEW)
        changeStatus(job, JiraTransitionCodes.REJECT)

    message = Message.get(name=MessageNames.PRINT_CANCELLED.name)
    commentStatus(job, message.text, False)


def send_reopen_job(job):
    """
    This will not always work. If the job is approved or done, there is currently no way to set it back to open or in progress.
    There may be jira transition codes that I don't know about, but they're difficult to find. Even if it doesn't work, the job should
    still be set to new in the DB and processed again, the status just won't match the actual progress of the print.
    """
    if job.print_status == PrintStatus.PRINTING:
        changeStatus(job, JiraTransitionCodes.STOP_PROGRESS)
    changeStatus(job, JiraTransitionCodes.REOPEN)
    message = Message.get(name=MessageNames.PRINT_QUEUED.name)
    commentStatus(job, message.text, False)


def send_print_finished(job):
    changeStatus(job, JiraTransitionCodes.READY_FOR_REVIEW)
    changeStatus(job, JiraTransitionCodes.APPROVE)
    commentStatus(job, job.Generate_Finish_Message())


def changeStatus(job, transitionCode):
    """
    Changes status of issue in Jira.
    See enumDefinitions JiraTransitionCodes for codes.
    """
    url = config['base_url'] + "/rest/api/2/issue/" + str(job.job_id) + "/transitions"
    headers = {
        "Content-type": "application/json",
        "Accept": "application/json"
    }
    data = {
        # "update": {
        #     "comment": [{
        #         "add": {
        #             "body": "The ticket is resolved"
        #         }
        #     }]
        # },
        "transition": {
            "id": str(transitionCode.value)
        }
    }

    try:
        response = requests.request(
            "POST",
            url,
            headers=headers,
            json=data,
            auth=auth
        )
    except requests.exceptions.Timeout as errt:
        print("Timeout Error while changing status for job: " + job.Get_Name())
        return False

    if not response.ok:
        print("Error updating status for job: " + job.Get_Name())
        # TODO: discord notification on timeout

    return response.ok


def commentStatus(job, comment, notify_user=True):
    """
    a simple function call to be used whenever you want to comment on a ticket
    """
    # Don't comment empty strings. Done so you can leave strings empty in the config if you don't want to send that message.
    if not comment:
        return

    url = config['base_url'] + "/rest/api/2/issue/" + str(job.job_id) + "/comment"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    if notify_user:
        payload = {
            "body": comment,
        }
    else:
        payload = {
            "body": comment,
            "visibility": {
                "type": "role",
                "value": "Project Members"
            },

        }

    try:
        response = requests.request(
            "POST",
            url,
            json=payload,
            headers=headers,
            auth=auth
        )
    except requests.exceptions.Timeout as errt:
        print("Timeout Error while commenting on job: " + job.Get_Name())
        return False
        # TODO: discord notification on timeout

    if not response.ok:
        print("Error commenting on job: " + job.Get_Name())
    return response.ok


def askedForStatus():
    """
    When someone asks what their print status if we reply
    """
    print("Checking for status updates...")
    url = config['base_url'] + "/rest/api/2/" + config['printing_url']
    headers = {
        "Accept": "application/json"
    }

    response = requests.request(
        "GET",
        url,
        headers=headers,
        auth=auth
    )

    # parse all open projects:
    openIssues = json.loads(json.dumps(json.loads(response.text), sort_keys=True, indent=4, separators=(",", ": ")))
    for issue in openIssues['issues']:
        url = issue['self']
        headers = {
            "Accept": "application/json"
        }

        response = requests.request(
            "GET",
            url,
            headers=headers,
            auth=auth
        )

        ticketID = url[url.find("issue/") + len("issue/"):url.rfind("")]
        singleIssue = json.loads(json.dumps(json.loads(response.text), sort_keys=True, indent=4, separators=(",", ": ")))
        comments = singleIssue['fields']['comment']['comments']
        comment = ''
        if len(comments) > 0:
            comment = comments[-1]['body']
        for trigger in config['requestUpdate']:
            if str(comment).find(trigger) != -1:
                print(comment)
                directory = r'jiradownloads'
                for filename in sorted(os.listdir(directory)):
                    if filename.find(ticketID):
                        commentStatus(ticketID, config["messages"]["statusInQueue"])
                printers = Printer.Get_All_Enabled()
                for printer in printers:
                    url = "http://" + printer.ip + "/api/job"
                    headers = {
                        "Accept": "application/json",
                        "Host": printer.ip,
                        "X-Api-Key": printer.api_key
                    }
                    try:
                        response = requests.request(
                            "GET",
                            url,
                            headers=headers
                        )
                        status = json.loads(json.dumps(json.loads(response.text), sort_keys=True, indent=4, separators=(",", ": ")))
                        if str(status['job']['file']['name']).find(ticketID) != -1:
                            base = config['messages']['statusUpdate'] + "\n"
                            completion = "Completion: " + str(round(status['progress']['completion'], 2)) + "%" + "\n"
                            eta = "Print time left: " + str(time.strftime('%H:%M:%S', time.gmtime(
                                status['progress']['printTimeLeft']))) + "\n"
                            material = "Cost: $" + str(round(
                                status['job']['filament']['tool0']['volume'] * printer.material_density *
                                config['payment']['costPerGram'], 2)) + "\n"
                            end = config['messages']['statusUpdateEnd']

                            printerStatusUpdate = base + completion + eta + material + end
                            commentStatus(ticketID, printerStatusUpdate)
                            print(printerStatusUpdate)
                    except requests.exceptions.RequestException as e:  # This is the correct syntax
                        print("Skipping " + printer + " due to network error.")
                return
