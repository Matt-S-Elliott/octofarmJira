import octoprint
import os
import flask
import jira
import print_job_handler
import invoice_generator
from classes.permissionCode import *
from classes.gcodeCheckItem import *
from pony.flask import Pony
import pythonFunctions
from classes.enumDefinitions import *
import yaml
from threading import Lock
from flask import Flask, render_template, session, request, copy_current_request_context, jsonify

with open("config_files/config.yml", "r") as yamlfile:
    config = yaml.load(yamlfile, Loader=yaml.FullLoader)

async_mode = None

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
thread = None
thread_lock = Lock()

DOWNLOAD_FOLDER = './jiradownloads'
CONFIG = './config_files/config.yml'

set_sql_debug(False)  # Shows the SQL queries pony is running in the console.
db.bind(provider='sqlite', filename='octofarmJira_database.sqlite', create_db=True)  # Establish DB connection.
db.generate_mapping(
    create_tables=True)  # Have to generate mapping to use Pony. Will create tables that do not already exist.

Pony(app)  # Connects routes to the DB as needed without having to do it manually.

@app.route('/')
def index():
    return flask.render_template('layout.html',  ip=flask.request.host)


@app.route('/printQueue')
def print_queue():
    return flask.render_template('queue/queue.html',  ip=flask.request.host)


@app.route('/printQueue/startPrint/<comment>/<job_id>', methods=['POST'])
def start_print(comment=None, job_id=None):
    """
    comment = string true or false
    job_id = string of job_id for job
    """
    try:
        job = PrintJob.get(job_id=int(job_id))
        if not job:
            return {'status': 'failed', 'reason': 'job_not_found'}
        if job.print_status != PrintStatus.IN_QUEUE.name:
            return {'status': 'failed', 'reason': 'job_not_in_queue'}
        if not job.printer_model.auto_start_prints:
            job.print_status = PrintStatus.PRINTING.name
            job.print_started_date = datetime.datetime.now()
            commit()
        elif job.printer_model.auto_start_prints:
            printer = octoprint.find_open_printer(job.printer_model)
            if not printer:
                return {'status': 'failed', 'reason': 'no_available_printer'}
            print_result = octoprint.start_print_job(job, printer, False)
            if not print_result:
                return {'status': 'failed', 'reason': 'failed_to_start_print'}

        if comment == 'true':
            result = jira.send_print_started(job)
            if not result:
                return {'status': 'failed', 'reason': 'comment_failed'}
        octoprint.printReceipt(job)
        return {'status': 'success'}
    except Exception as e:
        return {'status': 'failed', 'reason': repr(e)}


@app.route('/printQueue/cancelPrint/<job_id>', methods=['POST'])
def cancel_print(job_id=None):
    """ job_id = string of job_id for job """
    try:
        job = PrintJob.get(job_id=int(job_id))
        if not job:
            return {'status': 'failed', 'reason': 'job_not_found'}

        job.print_status = PrintStatus.CANCELLED.name
        commit()
        jira.send_print_cancelled(job)

        if os.path.exists(job.Get_File_Name()):
            os.remove(job.Get_File_Name())

        return {'status': 'success'}
    except Exception as e:
        return {'status': 'failed', 'reason': repr(e)}

@app.route('/printQueue/cancelAndRequeue/<job_id>', methods=['POST'])
def cancel_and_requeue(job_id=None):
    """ job_id = string of job_id for job """
    try:
        job = PrintJob.get(job_id=int(job_id))
        if not job:
            return {'status': 'failed', 'reason': 'job_not_found'}

        job.print_status = PrintStatus.CANCELLED.name
        commit()
        jira.send_print_cancelled(job)

        if os.path.exists(job.Get_File_Name()):
            os.remove(job.Get_File_Name())

        jira.send_reopen_job(job)
        job.print_status = PrintStatus.NEW.name
        job.printed_on = None
        job.print_started_date = None
        job.print_finished_date = None
        job.failure_message = None
        commit()
        return {'status': 'success'}

        return {'status': 'success'}
    except Exception as e:
        return {'status': 'failed', 'reason': repr(e)}



@app.route('/printQueue/markFinished/<comment>/<job_id>', methods=['POST'])
def mark_finished(comment=None, job_id=None):
    try:
        job = PrintJob.get(job_id=int(job_id))
        if not job:
            return {'status': 'failed', 'reason': 'job_not_found'}

        job.Mark_Job_Finished()

        if os.path.exists(job.Get_File_Name()):
            os.remove(job.Get_File_Name())

        sendComment = comment == 'true'
        jira.send_print_finished(job, sendComment)
        return {'status': 'success'}
    except Exception as e:
        return {'status': 'failed', 'reason': repr(e)}


@app.route('/printQueue/downloadGcode/<job_id>', methods=['GET'])
def download_gcode(job_id=None):
    try:
        job = PrintJob.get(job_id=int(job_id))
        if not job:
            return {'status': 'failed', 'reason': 'job_not_found'}

        if os.path.exists(job.Get_File_Name()):
            return flask.send_file(job.Get_File_Name(), as_attachment=True)

        gcode = print_job_handler.download_gcode(job)
        checked_gcode, check_result, weight, estimated_time, printer_model, fail_message = print_job_handler.check_gcode(
            gcode)
        if check_result == GcodeStates.VALID:
            generator = (cell for row in checked_gcode
                         for cell in row)
            file_name = job.Get_Name() + '.gcode'

            return flask.Response(generator,
                                  mimetype="text/plain",
                                  headers={"Content-Disposition": "attachment;filename=" + file_name})
        return {'status': 'failed', 'reason': 'gcode_state: ' + check_result.name}

    except Exception as e:
        return {'status': 'failed', 'reason': repr(e)}


@app.route('/printQueue/getQueue', methods=['GET'])
def get_queue():
    jobs = PrintJob.Get_Print_Queue_And_Printing()
    return jobs


@app.route('/printJobs')
def print_jobs():
    return flask.render_template('printJobs/print_jobs.html',  ip=flask.request.host)


@app.route('/printJobs/getJobs', methods=['GET'])
def get_jobs():
    jobs = PrintJob.Get_All_Print_Jobs_Screen(550)
    return jobs


@app.route('/printJobs/printReceipt/<job_id>', methods=['GET'])
def print_receipt(job_id):
    try:
        job = PrintJob.get(job_id=job_id)
        octoprint.printReceipt(job)
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/printJobs/queuePrint/<job_id>', methods=['POST'])
def queue_print(job_id):
    try:
        job = PrintJob.get(job_id=job_id)
        if not job:
            return {'status': 'failed', 'reason': 'job_not_found'}
        jira.send_reopen_job(job)
        job.print_status = PrintStatus.NEW.name
        job.printed_on = None
        job.print_started_date = None
        job.print_finished_date = None
        job.failure_message = None
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/printers')
def printers():
    all_printers = Printer.Get_All()
    return flask.render_template('printers/printers.html', printers=all_printers, 
                                 ip=flask.request.host)


@app.route('/printers/deletePrinter/<printer_id>', methods=['POST'])
def delete_printer(printer_id):
    try:
        Printer[printer_id].delete()
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/printers/togglePrinterStatus/<printer_id>', methods=['POST'])
def toggle_printer_status(printer_id):
    try:
        printer = Printer[printer_id]
        printer.enabled = not printer.enabled
        commit()
        return {'status': 'success', 'enabled': printer.enabled}
    except:
        return {'status': 'failed'}


@app.route('/printers/createPrinter', methods=['GET'])
def create_printer_get():
    printer_models = PrinterModel.Get_All()
    return flask.render_template('printers/create_printer.html', models=printer_models, 
                                 ip=flask.request.host)


@app.route('/printers/createPrinter', methods=['POST'])
def create_printer_post():
    try:
        form_data = request.form
        Printer.Add_From_Request(form_data)
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/printers/editPrinter/<printer_id>', methods=['GET'])
def edit_printer_get(printer_id):
    printer = Printer[printer_id]
    printer_models = PrinterModel.Get_All()
    return flask.render_template('printers/edit_printer.html', printer=printer, models=printer_models,
                                  ip=flask.request.host)


@app.route('/printers/editPrinter/<printer_id>', methods=['POST'])
def edit_printer_post(printer_id):
    try:
        form_data = request.form
        printer = Printer[printer_id]
        Printer.Map_Request(printer, form_data)
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/printers/connectPrinter/<printer_id>', methods=['POST'])
def connect_printer(printer_id):
    try:
        printer = Printer.get(id=printer_id)

        if (printer is None):
            return {'status': 'failed'}

        printer.Connect_Printer()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}

@app.route('/printers/testPrint/<printer_id>', methods=['POST'])
def test_print(printer_id):
    try:
        printer = Printer.get(id=printer_id)

        if (printer is None):
            return {'status': 'failed'}

        response = printer.Upload_Test_Print()
        if response.ok:
            return {'status': 'success'}
        return {'status': 'failed'}
    except:
        return {'status': 'failed'}


@app.route('/users')
def users():
    all_users = User.Get_All()
    return flask.render_template('users/users.html', users=all_users, 
                                 ip=flask.request.host)


@app.route('/users/toggleWhiteListed/<user_id>', methods=['POST'])
def toggle_white_listed_status(user_id):
    try:
        user = User[user_id]
        user.white_listed = not user.white_listed
        commit()
        return {'status': 'success', 'white_listed': user.white_listed}
    except:
        return {'status': 'failed'}


@app.route('/users/toggleBlackListed/<user_id>', methods=['POST'])
def toggle_black_listed_status(user_id):
    try:
        user = User[user_id]
        user.black_listed = not user.black_listed
        commit()
        return {'status': 'success', 'black_listed': user.black_listed}
    except:
        return {'status': 'failed'}


@app.route('/users/editUser/<user_id>', methods=['GET'])
def edit_user_get(user_id):
    user = User[user_id]
    return flask.render_template('users/edit_user.html', user=user, 
                                 ip=flask.request.host)


@app.route('/users/editUser/<user_id>', methods=['POST'])
def edit_user_post(user_id):
    try:
        form_data = request.form
        user = User[user_id]
        User.Map_Request(user, form_data)
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/permissionCodes')
def permissionCodes():
    all_codes = PermissionCode.Get_All()
    return flask.render_template('permissionCodes/permission_codes.html', permissionCodes=all_codes,
                                  ip=flask.request.host)
@app.route('/permissionCodes/getPermissionCodes')
def getPermissionCodes():
    all_codes = PermissionCode.Get_All(True)
    return all_codes

@app.route('/permissionCodes/addJobToPermissionCode/<code_id>/<job_id>', methods=['POST'])
def addJobToPermissionCode(code_id, job_id):
    try:
        job = PrintJob.get(job_id=int(job_id))
        permission_code = PermissionCode.Get_By_Id(int(code_id))
        if job.permission_code and job.permission_code.id == permission_code.id:
            job.permission_code = None
        else:
            job.permission_code = permission_code
        return {'status': 'success'}
    except Exception as e:
        return {'status': 'failed'}


@app.route('/permissionCodes/deletePermissionCode/<code_id>', methods=['POST'])
def delete_permission_code(code_id):
    try:
        if code_id == 1:  # ID 1 is always invalid code.
            return {'status': 'failed'}
        PermissionCode[code_id].delete()
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/permissionCodes/createPermissionCode', methods=['GET'])
def create_permission_code_get():
    return flask.render_template('permissionCodes/create_permission_code.html', 
                                 ip=flask.request.host)


@app.route('/permissionCodes/createPermissionCode', methods=['POST'])
def create_permission_code_post():
    try:
        form_data = request.form
        PermissionCode.Add_From_Request(form_data)
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/permissionCodes/editPermissionCode/<code_id>', methods=['GET'])
def edit_permission_code_get(code_id):
    permissionCode = PermissionCode[code_id]
    return flask.render_template('permissionCodes/edit_permission_code.html', permissionCode=permissionCode,
                                  ip=flask.request.host)


@app.route('/permissionCodes/editPermissionCode/<code_id>', methods=['POST'])
def edit_permission_code_post(code_id):
    try:
        if code_id == 1:  # ID 1 is always invalid code.
            return {'status': 'failed'}
        form_data = request.form
        code = PermissionCode[code_id]
        PermissionCode.Map_Request(code, form_data)
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}

@app.route('/permissionCodes/printJobsForPermissionCode/<code_id>', methods=['GET'])
def print_jobs_for_permission_code(code_id):
    permissionCode = PermissionCode[code_id]
    return flask.render_template('permissionCodes/print_jobs_for_permission_code.html', permissionCode=permissionCode,
                                  ip=flask.request.host)
@app.route('/permissionCodes/getPrintJobsForPermissionCode/<code_id>', methods=['GET'])
def get_print_jobs_for_permission_code(code_id):
    jobs = PrintJob.Get_Jobs_For_View_Jobs_For_Permission_Code(code_id)
    return jobs


@app.route('/permissionCodes/getInvoice/<code_id>', methods=['GET'])
def get_invoice_for_permission_code(code_id):
    filename = invoice_generator.generate_invoice(code_id)
    return flask.send_from_directory("", filename, as_attachment=True)

@app.route('/permissionCodes/getAllInvoices', methods=['GET'])
def get_all_invoices():
    all_codes = PermissionCode.Get_All()
    for code in all_codes:
        filename = invoice_generator.generate_invoice(code.id)

    return "All invoiced!"

@app.route('/messages')
def messages():
    all_messages = Message.Get_All()
    message_names = get_dict(MessageNames)
    return flask.render_template('messages/messages.html', messages=all_messages, message_names=message_names,
                                  ip=flask.request.host)


@app.route('/messages/deleteMessage/<message_id>', methods=['POST'])
def delete_message(message_id):
    try:
        Message[message_id].delete()
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/messages/createMessage', methods=['GET'])
def create_message_get():
    return flask.render_template('messages/create_message.html',  ip=flask.request.host)


@app.route('/messages/createMessage', methods=['POST'])
def create_message_post():
    try:
        form_data = request.form
        Message.Add_From_Request(form_data)
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/messages/editMessage/<message_id>', methods=['GET'])
def edit_message_get(message_id):
    message = Message[message_id]
    return flask.render_template('messages/edit_message.html', message=message, 
                                 ip=flask.request.host)


@app.route('/messages/editMessage/<message_id>', methods=['POST'])
def edit_message_post(message_id):
    try:
        form_data = request.form
        message = Message[message_id]
        Message.Map_Request(message, form_data)
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/keywords')
def keywords():
    all_keywords = Keyword.Get_All()
    return flask.render_template('keywords/keywords.html', keywords=all_keywords, 
                                 ip=flask.request.host)


@app.route('/keywords/deleteKeyword/<keyword_id>', methods=['POST'])
def delete_keyword(keyword_id):
    try:
        Keyword[keyword_id].delete()
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/keywords/createKeyword', methods=['GET'])
def create_keyword_get():
    return flask.render_template('keywords/create_keyword.html',  ip=flask.request.host)


@app.route('/keywords/createKeyword', methods=['POST'])
def create_keyword_post():
    try:
        form_data = request.form
        Keyword.Add_From_Request(form_data)
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/keywords/editKeyword/<keyword_id>', methods=['GET'])
def edit_keyword_get(keyword_id):
    keyword = Keyword[keyword_id]
    return flask.render_template('keywords/edit_keyword.html', keyword=keyword, 
                                 ip=flask.request.host)


@app.route('/keywords/editKeyword/<keyword_id>', methods=['POST'])
def edit_keyword_post(keyword_id):
    try:
        form_data = request.form
        keyword = Keyword[keyword_id]
        Keyword.Map_Request(keyword, form_data)
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/printerModels')
def printer_models():
    all_models = PrinterModel.Get_All()
    return flask.render_template('printerModels/printer_models.html', printer_models=all_models,
                                  ip=flask.request.host)


@app.route('/printerModels/deletePrinterModel/<printer_model_id>', methods=['POST'])
def delete_printer_model(printer_model_id):
    try:
        PrinterModel[printer_model_id].delete()
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/printerModels/createPrinterModel', methods=['GET'])
def create_printer_model_get():
    all_keywords = Keyword.Get_All()
    return flask.render_template('printerModels/create_printer_model.html', all_keywords=all_keywords,
                                  ip=flask.request.host)


@app.route('/printerModels/createPrinterModel', methods=['POST'])
def create_printer_model_post():
    try:
        form_data = request.form
        PrinterModel.Add_From_Request(form_data)
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/printerModels/editPrinterModel/<printer_model_id>', methods=['GET'])
def edit_printer_model_get(printer_model_id):
    all_keywords = Keyword.Get_All()
    printer_model = PrinterModel[printer_model_id]
    return flask.render_template('printerModels/edit_printer_model.html', printer_model=printer_model,
                                 all_keywords=all_keywords,  ip=flask.request.host)


@app.route('/printerModels/editPrinterModel/<printer_model_id>', methods=['POST'])
def edit_printer_model_post(printer_model_id):
    try:
        form_data = request.form
        printer_model = PrinterModel[printer_model_id]
        PrinterModel.Map_Request(printer_model, form_data)
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/checkItems')
def check_items():
    all_check_items = GcodeCheckItem.Get_All()
    return flask.render_template('checkItems/check_items.html', check_items=all_check_items,
                                  ip=flask.request.host)


@app.route('/checkItems/deleteCheckItem/<check_item_id>', methods=['POST'])
def delete_check_item(check_item_id):
    try:
        GcodeCheckItem[check_item_id].delete()
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/checkItems/createCheckItem', methods=['GET'])
def create_check_item_get():
    printer_models = PrinterModel.Get_All()
    messages = Message.Get_All()
    check_actions = get_dict(GcodeCheckActions)
    return flask.render_template('checkItems/create_check_item.html', printer_models=printer_models, messages=messages,
                                 check_actions=check_actions,  ip=flask.request.host)


@app.route('/checkItems/createCheckItem', methods=['POST'])
def create_check_item_post():
    try:
        form_data = request.form
        GcodeCheckItem.Add_From_Request(form_data)
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}


@app.route('/checkItems/editCheckItem/<check_item_id>', methods=['GET'])
def edit_check_item_get(check_item_id):
    printer_models = PrinterModel.Get_All()
    messages = Message.Get_All()
    check_actions = get_dict(GcodeCheckActions)
    check_item = GcodeCheckItem[check_item_id]
    return flask.render_template('checkItems/edit_check_item.html', check_item=check_item,
                                 printer_models=printer_models, messages=messages, check_actions=check_actions,
                                  ip=flask.request.host)


@app.route('/checkItems/editCheckItem/<check_item_id>', methods=['POST'])
def edit_check_item_post(check_item_id):
    try:
        form_data = request.form
        check_item = GcodeCheckItem[check_item_id]
        GcodeCheckItem.Map_Request(check_item, form_data)
        commit()
        return {'status': 'success'}
    except:
        return {'status': 'failed'}

@app.route('/delete/<fileName>', methods=['GET', 'POST'])
def remove(fileName=None):
    abs_path = os.path.join(DOWNLOAD_FOLDER, fileName)
    pythonFunctions.delete(abs_path)
    files = os.listdir(DOWNLOAD_FOLDER)
    return flask.render_template('queue.html', files=files, ip=flask.request.host)


@app.route('/download/<path:filename>', methods=['GET', 'POST'])
def download(filename):
    return flask.send_from_directory(DOWNLOAD_FOLDER, filename, as_attachment=True)


if __name__ == '__main__':
    app.run(host='localhost', port=10001)
    # app.run(host='localhost', port=10001, allow_unsafe_werkzeug=True)
    # werkzeug is a development http server not meant for production, but it is fine for us because we do not experience heavy loads.
