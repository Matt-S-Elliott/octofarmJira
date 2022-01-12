import requests
import schedule
import time
from requests.auth import HTTPBasicAuth
import json
import yaml
import jira
import os
import time
from datetime import datetime

with open("config.yml", "r") as yamlfile:
    config = yaml.load(yamlfile, Loader=yaml.FullLoader)
with open("printers.yml", "r") as yamlfile:
    printers = yaml.load(yamlfile, Loader=yaml.FullLoader)

def TryPrintingFile(file):
    for printer in printers['PRINTERS']:
        apikey = printers['PRINTERS'][printer]['api']
        printerIP = printers['PRINTERS'][printer]['ip']
        url = "http://" + printerIP + "/api/job"

        headers = {
            "Accept": "application/json",
            "Host": printerIP,
            "X-Api-Key": apikey
        }
        try:
            response = requests.request(
                "GET",
                url,
                headers=headers
            )
            status = json.loads(json.dumps(json.loads(response.text), sort_keys=True, indent=4, separators=(",", ": ")))
            if str(status['state']) == "Operational" and str(status['progress']['completion']) != "100.0":
                uploadFileToPrinter(apikey, printerIP, file)
                return
        except requests.exceptions.RequestException as e:  # This is the correct syntax
            print("Skipping " + printer + " due to network error")


def GetStatus(ip, api):
    apikey = api
    printerIP = ip
    url = "http://" + printerIP + "/api/job"

    headers = {
        "Accept": "application/json",
        "Host": printerIP,
        "X-Api-Key": apikey
    }
    try:
        response = requests.request(
            "GET",
            url,
            headers=headers
        )
        status = json.loads(json.dumps(json.loads(response.text), sort_keys=True, indent=4, separators=(",", ": ")))
        return status
    except requests.exceptions.RequestException as e:  # This is the correct syntax
            print(printerIP + "'s raspberry pi is offline and can't be contacted over the network")
            status = "offline"
            return status

def receiptPrinter(scrapedprNumber, scrapedPatronName, printer=''):
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    from escpos.printer import Usb
    try:
        #try to reconnect to printer
        p = Usb(0x0416, 0x5011, 0, 0x81, 0x03)
    except:
        alreadyConnected = True
    try:
        #try to center printing alignment
        p.set(align='center')
    except:
        alreadyAligned = True
    #create new image large enough to fit super long names
    img = Image.new('RGB', (2400, 400), color = (0, 0, 0))
    fnt = ImageFont.truetype(r"recources/arialbd.ttf", 110, encoding="unic")
    tiny = ImageFont.truetype(r"recources/arial.ttf", 20, encoding="unic")
    d = ImageDraw.Draw(img)
    d.text((32,0), scrapedprNumber, font=fnt, fill=(255, 255, 255))
    firstFew = scrapedPatronName[:8]
    if 'y' in firstFew or 'g' in firstFew or 'p' in firstFew or 'q' in firstFew:
        d.text((32,121), scrapedPatronName, font=fnt, fill=(255, 255, 255))
    else:
        d.text((32,128), scrapedPatronName, font=fnt, fill=(255, 255, 255))

    d.text((34, 256), printer, font=tiny, fill=(255, 255, 255))

    imageBox = img.getbbox()
    cropped=img.crop(imageBox)
    inverted = ImageOps.invert(cropped)
    rotated = inverted.rotate(270, expand=True)
    
    try:
        #print image
        p.image(rotated)
        #cut point
        p.text("\n\n-                              -\n\n")
    except:
        print("\nThe receipt printer is unplugged or not powered on, please double check physical connections.")
        raise ValueError



def uploadFileToPrinter(apikey, printerIP, file):
    fle={'file': open('jiradownloads/' + file + '.gcode', 'rb'), 'filename': file}
    url="http://" + printerIP + "/api/files/{}".format("local")
    payload={'select': 'true','print': 'true' }
    header={'X-Api-Key': apikey}
    response = requests.post(url, files=fle,data=payload,headers=header)
    with open('jiradownloads/' + file + '.gcode', 'rb') as fh:
        first = next(fh).decode()
    try:
        grams = first.split('GRAMS')[1].split(',')[0].strip('=')
    except:
        grams = ''
    try:
        printTime = first.split('TIME')[1].split(',')[0].strip('=')
    except:
        printTime = ''
    try:
        taxExempt = first.split('TAXEXEMPT=')[1].split(',')[0]
    except:
        taxExempt = ''
    startTime = datetime.now().strftime("%I:%M" '%p')
    if startTime[0] == '0':
        startTime = startTime[1:]
    #print(str(grams) + "  " + printTime + " " + startTime + " " + str(taxExempt))
    if grams != '' and printTime != '' and taxExempt != '':
        ticketText = "\nPrint was started at " + str(startTime) + "\nEstimated print weight is " + str(grams) + "g" + "\nEstimated print time is " + printTime
        if taxExempt == "True":
            ticketText += "\nEstimated print cost is ("+str(grams)+"g * $0.05/g) = $"
            cost = float(grams) * .05
            cost = str(("%.2f" % (cost)))
            ticketText += cost + ' (tax exempt)'
        elif taxExempt == "False":
            ticketText += "\nEstimated print cost is ("+str(grams)+"g * $0.05/g * 1.0775 state tax = $"
            cost = float(grams) * .05 * 1.0775
            cost = str(("%.2f" % (cost)))
            ticketText += cost
    else:
        ticketText = "Your file is now printing and we will update you when it is finished and ready for pickup"
    
    if os.path.exists("jiradownloads/" + file + ".gcode"):
        #print(config['Save_printed_files'])
        if config['Save_printed_files'] == False:
            os.remove("jiradownloads/" + file + ".gcode")
        else:
            os.replace("jiradownloads/" + file + ".gcode", "archive_files/" + file + ".gcode")
<<<<<<< Updated upstream
        jira.commentStatus(file, "Your file is now printing and we will update you when it is finished and ready for pickup")
        print("Now printing: " + file + " on " + printerIP)
=======
        if config["Make_files_anon"] == True:
            jira.commentStatus(file, ticketText)
            print("Now printing: " + file + " on " + printerIP)
        else:
            jira.commentStatus(file, ticketText)
            print("Now printing: " + file + " on " + printerIP)
>>>>>>> Stashed changes
        
def resetConnection(apikey, printerIP):
    url="http://" + printerIP + "/api/connection"
    disconnect={'command': 'disconnect'}
    connect={'command': 'connect'}
    header={'X-Api-Key': apikey}
    response = requests.post(url,json=disconnect,headers=header)
    time.sleep(30)
    response = requests.post(url,json=connect,headers=header)

def PrintIsFinished():
    for printer in printers['PRINTERS']:
        apikey = printers['PRINTERS'][printer]['api']
        printerIP = printers['PRINTERS'][printer]['ip']
        url = "http://" + printerIP + "/api/job"
        headers = {
            "Accept": "application/json",
            "Host": printerIP,
            "X-Api-Key": apikey
        }
        try:
            response = requests.request(
                "GET",
                url,
                headers=headers
            )
            if(json.loads(json.dumps(json.loads(response.text), sort_keys=True, indent=4, separators=(",", ": ")))):
                status = json.loads(json.dumps(json.loads(response.text), sort_keys=True, indent=4, separators=(",", ": ")))
            else:
                status = "offline"
        except requests.exceptions.RequestException as e:  # This is the correct syntax
            print(printer + "'s raspberry pi is offline and can't be contacted over the network")
            status = "offline"
            
        """
        I might want to change some of this code when I am in front of the printers to make it so each printers status get's printed out
        """
        if status != "offline":
            if status['state'] == "Operational":
                if str(status['progress']['completion']) == "100.0":
                    print(printer + " is finishing up")
                    file = os.path.splitext(status['job']['file']['display'])[0]
                    resetConnection(apikey, printerIP)
                    if config['Save_printed_files'] == True:
                        with open("archive_files/" + file + ".gcode", 'rb') as fh:
                            first = next(fh).decode()
                        #print("archive files first line print test")
                        #print(first)
                        try:
                            grams = first.split('GRAMS=')[1].split(',')[0]
                        except:
                            grams = ''
                        try:
                            taxExempt = first.split('TAXEXEMPT=')[1].split(',')[0]
                        except:
                            taxExempt = ''
                        if grams and taxExempt == '':
                            jira.commentStatus(file, "Your print has been completed and should now be available for pickup")
                        else:
                            response = "{color:#00875A}Print completed successfully!{color}\n\nPrint was harvested at "
                            startTime = datetime.now().strftime("%I:%M" '%p')
                            if startTime[0] == '0':
                                startTime = startTime[1:]
                            response += startTime + "\nFilament Usage ... " + grams + "g\n"
                            if taxExempt == False:
                                response += "Actual Cost ... ("+grams+"g * $0.05/g) * 1.0775 state tax = $"
                                cost = float(grams) * .05 * 1.0775
                                cost = str(("%.2f" % (cost)))
                                response += cost + '\n\nYour link to pay online will be generated by my supervisor as soon as they are available. Your print is ready for pickup by the orange pillars in the ProtoSpace on the 2nd floor of the library whenever the library is open. Thanks!'
                            else:
                                response += "Actual Cost ... ("+grams+"g * $0.05/g) = $"
                                cost = float(grams) * .05
                                cost = str(("%.2f" % (cost)))
                                response += cost + ' (tax exempt)\n\nYour print is ready for pickup by the orange pillars in the ProtoSpace on the 2nd floor of the library whenever the library is open. Thanks!'
                                jira.commentStatus(file, response)
                    else:
                        jira.commentStatus(file, "Your print has been completed and should now be available for pickup")
                    jira.changeStatus(file, "21")
                    jira.changeStatus(file, "31")
                    if config['payment']['prepay'] == True:
                        jira.changeStatus(file, "41")
                else:
                    print(printer + " is ready")
                    continue
            elif status['state'] == "Printing":
                print(printer + " is printing")
            else:
                print(printer + " is offline")


def eachNewFile():
    directory = r'jiradownloads'
    for filename in os.listdir(directory):
        if filename.endswith(".gcode") or filename.endswith(".stl"):
            TryPrintingFile(os.path.splitext(filename)[0])
        else:
            continue
