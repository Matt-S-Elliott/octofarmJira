import yaml
import jira
from classes.gcodeLine import GcodeLine
from classes.permissionCode import *
from classes.gcodeCheckItem import *
from classes.enumDefinitions import *
import re
from classes.mLibraryValidator import MLibraryValidator

# load all of our config files
from classes.printerModel import PrinterModel

with open("config_files/config.yml", "r") as yamlFile:
    config = yaml.load(yamlFile, Loader=yaml.FullLoader)

drive_api_key = config['google_drive_api_key']


@db_session
def process_new_jobs():
    print("Checking DB for new jobs...")
    new_jobs = PrintJob.Get_All_By_Status(PrintStatus.NEW)
    print(str(len(new_jobs)) + " new jobs found.")
    print(new_jobs)

    for job in new_jobs:
        if not job.gcode_url:  # If there is no gcode_url, no files were attached.
            handle_job_failure(job, MessageNames.NO_FILE_ATTACHED)
            continue

        elif config["use_naughty_list"] is True and job.user.black_listed:
            handle_job_failure(job, MessageNames.BLACK_LIST_FAIL)
            continue

        elif config["use_nice_list"] is True and not job.user.white_listed:
            handle_job_failure(job, MessageNames.WHITE_LIST_FAIL)
            continue

        elif job.permission_code:  # If there is a permission code, validate it.

            # Validations specific to a certain system of funding codes happen first. 
            # If you have no specific checks, comment out this section
            code_state = PermissionCode.Use_Validation_Module(MLibraryValidator, job.permission_code.code)
            if code_state == PermissionCodeStates.VALIDATOR_FAIL:
                handle_job_failure(job, MessageNames.PERMISSION_VALIDATOR_FAIL)
                continue

            # Check if code is present in internal permission code list
            code_state = PermissionCode.Validate_Permission_Code(job.permission_code.code)
            if code_state == PermissionCodeStates.INVALID:
                handle_job_failure(job, MessageNames.PERMISSION_CODE_INVALID)
                continue
            elif code_state == PermissionCodeStates.EXPIRED:
                handle_job_failure(job, MessageNames.PERMISSION_CODE_EXPIRED)
                continue
            elif code_state == PermissionCodeStates.NOT_YET_ACTIVE:
                handle_job_failure(job, MessageNames.PERMISSION_CODE_NOT_YET_ACTIVE)
                continue

            
        gcode = download_gcode(job)

        if gcode == "ERROR":
            handle_job_failure(job, MessageNames.UNKNOWN_DOWNLOAD_ERROR)
            continue
        elif gcode == "ERROR_403":
            handle_job_failure(job, MessageNames.GOOGLE_DRIVE_403_ERROR)
            continue
        else:
            checked_gcode, check_result, weight, estimated_time, printer_model, fail_message, soft_fail_messages = check_gcode(gcode, job.printer_model)
            if check_result == GcodeStates.VALID:
                text_file = open(job.Get_File_Name(), "w")
                n = text_file.write(checked_gcode)
                text_file.close()
                job.print_status = PrintStatus.IN_QUEUE.name
                job.weight = weight
                job.print_time = estimated_time
                job.printer_model = printer_model
                # TODO: If printer_model is not a manual start one, send a notification to discord or something
                if job.permission_code:
                    job.cost = round(weight * 0.05, 2)
                else:
                    job.cost = round(weight * 0.05 * 1.0775, 2)
                commit()
                jira.send_print_queued(job)
                for message in soft_fail_messages:
                    jira.commentStatus(job, message.text, True)
            elif check_result == GcodeStates.INVALID:
                handle_job_failure(job, fail_message.name if fail_message else MessageNames.GCODE_CHECK_FAIL)
            elif check_result == GcodeStates.NO_PRINTER_MODEL:
                handle_job_failure(job, MessageNames.NO_PRINTER_MODEL)


def download_gcode(job):
    try:
        if job.url_type == UrlTypes.JIRA_ATTACHMENT.name:
            return jira.download(job)
        elif job.url_type == UrlTypes.GOOGLE_DRIVE.name:
            return downloadGoogleDrive(job)
        elif job.url_type == UrlTypes.UNKNOWN.name:
            return "ERROR"
    except:
        return "ERROR"


def downloadGoogleDrive(job):
    """
    if the jira project has a Google Drive link in the description download it
    """
    url = 'https://www.googleapis.com/drive/v3/files/' + job.gcode_url + '/?key=' + drive_api_key + '&alt=media'

    headers = {
        "Accept": "application/json"
    }

    try:
        response = requests.request(
            "GET",
            url,
            headers=headers,
        )
    except Exception as e:
        print("Ticket " + job.Get_Name() + " error while downloading gcode from google drive.")
        print(e)
        return "ERROR"

    if response.ok:
        return response.text
    elif response.status_code == 403:
        return "ERROR_403"
    else:
        print("Ticket " + job.Get_Name() + ": " + str(response.status_code) + " while downloading gcode from google drive.")
        return "ERROR"


def handle_job_failure(job, message_name):
    message = Message.get(name=message_name if type(message_name) is str else message_name.name)
    if message:
        job.failure_message = message.id
        jira.send_fail_message(job, message.text)
    else:
        print("No message found for:", message_name)
        print("Suggest adding it in the admin panel.")
    job.print_status = PrintStatus.CANCELLED.name
    commit()


def parse_gcode(gcode):
    """
    Parses a .gcode file into a list of GcodeLine objects.
    Empty lines are ignored and not added.
    """
    try:
        gcode = gcode.split("\n")
        parsed_gcode = []
        for line in gcode:
            if line:  # Filter out empty lines.
                commentIndex = 0  # Start at 0 so we enter the loop.
                comment = ""
                while commentIndex >= 0:  # Find any comments.
                    commentIndex = line.find(';')  # Will be -1 if no comments found.
                    if commentIndex >= 0:
                        comment = comment + line[commentIndex + 1:].strip()  # Pull out the comment
                        line = line[:commentIndex]  # Remove it from the line.
                if line:  # If there is anything left in the line keep going.
                    split_line = line.split()
                    parsed_gcode.append(GcodeLine(split_line[0], split_line[1:], comment))
                else:  # If nothing is left at this point, the line is purely a comment.
                    parsed_gcode.append(GcodeLine(';', None, comment))
        return parsed_gcode
    except Exception as e:
        return []


def gcode_to_text(parsed_gcode):
    """
    Turns a list of GcodeLine objects into plain text suitable to be written to a text file and run on a printer.
    """
    startSeconds = time.time()
    text_gcode = ''
    lines = []
    for line in parsed_gcode:
        new_line = ''
        new_line += line.command + ' '
        if line.params:
            new_line += ' '.join(line.params)
        if line.comment and line.command != ';':
            new_line += ' ;'
        if line.comment:
            new_line += line.comment
        lines.append(new_line)

    joinedLines = '\n'.join(lines)
    print("Time to process .gcode: " + (str)(time.time() - startSeconds))
    return joinedLines


def filter_characters(string):
    """Removes all characters from a string except for numbers."""
    return re.sub("\D", "", string)


def convert_time_to_seconds(time_string):
    """Converts a string with format 1d 1h 0m 12s into seconds."""
    split = time_string.split()  # Get each element.
    split.reverse()  # Reverse so seconds are the first element.
    result = 0
    for i in range(len(split)):  # Iterate over each element and multiply by the amount of seconds in it.
        if i == 3:  # Days
            result += int(filter_characters(split[i])) * 86400
        elif i == 2:  # Hours
            result += int(filter_characters(split[i])) * 3600
        elif i == 1:  # Minutes
            result += int(filter_characters(split[i])) * 60
        elif i == 0:  # Seconds
            result += int(filter_characters(split[i]))

    return result


def check_gcode(file, printer_model):
    """
    Check if gcode fits the requirements that we have set in the config
    """
    
    parsedGcode = parse_gcode(file)
    weight = 0
    estimated_time = ''
    printer_model = ''
    soft_fail_messages = []

    if len(parsedGcode) == 0:
        return None, GcodeStates.INVALID, 0, 0, None, None, soft_fail_messages

    index = len(parsedGcode) - 1
    while (weight == 0 or estimated_time == '' or printer_model == '') and index > 0:
        comment = parsedGcode[index].comment
        if comment.startswith('estimated printing time (normal mode) ='):
            split = comment.split('=')
            estimated_time = convert_time_to_seconds(split[1].strip())
        elif comment.startswith('total filament used [g] ='):
            split = comment.split('=')
            weight = float(split[1].strip())
        elif comment.startswith('printer_notes'):
            models = PrinterModel.Get_All()
            for m in models:
                if m.keyword.value in comment:
                    printer_model = m.id
                    continue
        index -= 1

    check_items = GcodeCheckItem.Get_All_For_Model(printer_model)

    for check_item in check_items:
        if GcodeCheckActions[check_item.check_action] is GcodeCheckActions.REMOVE_COMMAND_ALL:
            file_length = len(parsedGcode)
            for i in range(len(parsedGcode)):
                if i < file_length and parsedGcode[i].command == check_item.command:
                    file_length -= 1
                    parsedGcode.pop(i)

        elif GcodeCheckActions[check_item.check_action] is GcodeCheckActions.ADD_COMMAND_AT_END:
            parsedGcode.append(GcodeLine(check_item.command, check_item.action_value, ''))

        elif GcodeCheckActions[check_item.check_action] is GcodeCheckActions.COMMAND_MUST_EXIST:
            commandFound = False
            for line in parsedGcode:
                if line.command == check_item.command and line.command != ';':  # If it is not a comment, only check that the command is there.
                    commandFound = True
                    break
                elif line.command == check_item.command and line.command == ';':  # If it is a comment, ensure the string matches.
                    if check_item.action_value.lower().strip() in line.comment.lower().strip():
                        commandFound = True
                        break
            if not commandFound:
                return None, GcodeStates.INVALID, 0, 0, printer_model, check_item.message, soft_fail_messages

        elif GcodeCheckActions[check_item.check_action] is GcodeCheckActions.COMMAND_PARAM_MIN:
            for line in parsedGcode:
                if line.command == check_item.command:
                    value = int(filter_characters(line.params[0]))  # Get int value of first param.
                    if value < int(check_item.action_value):
                        return None, GcodeStates.INVALID, 0, 0, printer_model, check_item.message, soft_fail_messages

        elif GcodeCheckActions[check_item.check_action] is GcodeCheckActions.COMMAND_PARAM_MAX:
            for line in parsedGcode:
                if line.command == check_item.command:
                    value = int(filter_characters(line.params[0]))  # Get int value of first param.
                    if value > int(check_item.action_value):
                        return None, GcodeStates.INVALID, 0, 0, printer_model, check_item.message, soft_fail_messages

        elif GcodeCheckActions[check_item.check_action] is GcodeCheckActions.KEYWORD_CHECK:
            keyword = Keyword.get(id=check_item.action_value)
            keywordFound = False;
            for line in parsedGcode:
                if line.comment.startswith('printer_notes') and keyword.value in line.comment:
                    keywordFound = True;
                    break
            if not keywordFound and check_item.hard_fail:
                return None, GcodeStates.INVALID, 0, 0, printer_model, check_item.message, soft_fail_messages
            elif not keywordFound and not check_item.hard_fail:
                soft_fail_messages.append(check_item.message)
                

    if printer_model == '':  # Putting this down here so that other checks will be hit first.
        return None, GcodeStates.NO_PRINTER_MODEL, 0, 0, printer_model, None, soft_fail_messages

    text_gcode = gcode_to_text(parsedGcode)
    return text_gcode, GcodeStates.VALID, weight, estimated_time, printer_model, None, soft_fail_messages
