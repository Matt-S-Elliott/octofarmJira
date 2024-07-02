from reportlab.lib import colors
from reportlab.lib.pagesizes import letter

import jira
from classes.class_imports import *
from datetime import date, timedelta
import os

from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.units import inch

WIDTH = letter[0]
HEIGHT = letter[1]
LEFT_MARGIN = 0.5 * inch
TOP_MARGIN = 0.5 * inch


def first_page(canvas, doc):
    canvas.saveState()

    # logo
    mask = [0, 0, 0, 0, 0, 0]
    canvas.drawImage("marriott-library-logo.png", LEFT_MARGIN, HEIGHT - TOP_MARGIN, width=148, height=22, mask=mask)

    # invoice text
    canvas.setFillColorRGB(0.6, 0.6, 0.6)
    canvas.setStrokeColorRGB(0.6, 0.6, 0.6)
    canvas.setFont('Times-Roman', 22)
    canvas.drawString(WIDTH - 2 * inch, HEIGHT - TOP_MARGIN, "INVOICE")

    # horizontal line
    canvas.line(1 * inch, HEIGHT - TOP_MARGIN - .25 * inch, WIDTH - 1 * inch, HEIGHT - TOP_MARGIN - .25 * inch)

    # address text
    canvas.setFont('Times-Roman', 10)
    canvas.drawString(1 * inch, HEIGHT - TOP_MARGIN - .5 * inch, "J. Willard Marriott Library")
    canvas.drawString(1 * inch, HEIGHT - TOP_MARGIN - .7 * inch, "295 South 1500 East")
    canvas.drawString(1 * inch, HEIGHT - TOP_MARGIN - .9 * inch, "Salt Lake City, UT 84112")
    canvas.drawString(1 * inch, HEIGHT - TOP_MARGIN - 1.1 * inch, "p. 801-581-8558")

    # to line
    canvas.setFont('Times-Roman', 12)
    canvas.drawString(1 * inch, HEIGHT - TOP_MARGIN - 1.5 * inch, "To: " + doc.To)
    canvas.drawString(1 * inch, HEIGHT - TOP_MARGIN - 1.8 * inch, "Funding Code: " + doc.Code_Name)

    # invoice number and date
    canvas.setFont('Times-Roman', 11)
    canvas.drawString(WIDTH - 3.1 * inch, HEIGHT - TOP_MARGIN - .5 * inch, "Invoice Number:")
    today = date.today()
    invoice_number = str(today.month) + str(today.day) + str(today.year) + str(doc.Code_Id)
    canvas.drawString(WIDTH - 1.9 * inch, HEIGHT - TOP_MARGIN - .5 * inch, invoice_number)
    canvas.drawString(WIDTH - 2.4 * inch, HEIGHT - TOP_MARGIN - .7 * inch, "Date:")
    canvas.drawString(WIDTH - 1.9 * inch, HEIGHT - TOP_MARGIN - .7 * inch, str(date.today()))
    canvas.line(WIDTH - 2.05 * inch,
                HEIGHT - TOP_MARGIN - .52 * inch,
                WIDTH - 1 * inch,
                HEIGHT - TOP_MARGIN - .52 * inch)
    canvas.line(WIDTH - 2.05 * inch,
                HEIGHT - TOP_MARGIN - .72 * inch,
                WIDTH - 1 * inch,
                HEIGHT - TOP_MARGIN - .72 * inch)

    # page number
    canvas.setFillColor(colors.black)
    canvas.setStrokeColor(colors.black)
    canvas.setFont('Times-Roman', 9)
    canvas.drawString(inch, 0.75 * inch, "Page %s" % (doc.page))
    canvas.restoreState()


def other_pages(canvas, doc):
    canvas.saveState()
    canvas.setFont('Times-Roman', 9)
    canvas.drawString(inch, 0.75 * inch, "Page %d" % doc.page)
    canvas.restoreState()


def generate_contact_table():
    LIST_STYLE = TableStyle(
        [
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), .5, colors.lightgrey),
            ('ALIGNMENT', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]
    )
    data = [["Contact", "Title", "Payment Terms", "Due Date"],
            ["Erika Church", "Design & Technology\n Coordinator", "01-00790-2000-28768--40585",
             str(date.today() + timedelta(days=10))]]
    table = Table(data,
                  colWidths=[2 * inch, 2 * inch, 2 * inch, 2 * inch],
                  rowHeights=None,
                  style=LIST_STYLE,
                  splitByRow=1,
                  repeatRows=1,
                  repeatCols=0,
                  rowSplitRange=None,
                  spaceBefore=None,
                  spaceAfter=None,
                  cornerRadii=None)
    return table


def generate_job_table(print_jobs):
    LIST_STYLE = TableStyle(
        [
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('LINEBELOW', (0, 0), (-1, 0), .5, colors.black),
            ('LINEBELOW', (0, 1), (-1, -4), .5, colors.lightgrey),
            ('LINEBELOW', (0, -4), (-1, -4), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, (.91, .91, .91)]),
            ('ALIGNMENT', (2, 0), (3, -1), 'RIGHT'),
            ('NOSPLIT', (0, -3), (-1, -1))
        ]
    )
    data = [["QTY", "Description", "Unit Price", "Line Total"]]
    # sets up the columns and rows for the table
    total = 0
    for pj in print_jobs:
        # setup for each row
        row = []
        qty = 1
        row.append(qty)
        row.append(pj.job_name)
        row.append("${:,.2f}".format(pj.cost))
        row.append("${:,.2f}".format(pj.cost * qty))
        total += pj.cost * qty
        # add the row to the table
        data.append(row)

    currency_string = "${:,.2f}".format(total)

    data.append(["", "", "Subtotal", currency_string])
    data.append(["", "", "Sales Tax", "Tax Exempt"])
    data.append(["", "", "Total", currency_string])

    table = Table(data,
                  colWidths=[inch, 3 * inch, inch, inch],
                  rowHeights=None,
                  style=LIST_STYLE,
                  splitByRow=1,
                  repeatRows=1,
                  repeatCols=0,
                  rowSplitRange=None,
                  spaceBefore=None,
                  spaceAfter=None,
                  cornerRadii=None)
    return table


def mark_jobs_invoiced(print_jobs):
    for pj in print_jobs:
        pj.Mark_Job_Invoiced()
        jira.send_print_invoiced(pj)


def generate_invoice(permission_code_id):
    print_jobs = PrintJob.Get_Jobs_For_Permission_Code_Not_Invoiced(permission_code_id)
    permission_code = PermissionCode.Get_By_Id(permission_code_id)
    if not os.path.exists("Invoices/" + str(date.today())):
        os.makedirs("Invoices/" + str(date.today()))
    doc_name = "Invoices/" + str(date.today()) + "/" + permission_code.name + "_" + str(date.today()) + "_" + "Invoice.pdf"
    doc = SimpleDocTemplate(doc_name, pagesize=letter)
    doc.To = permission_code.contact_info
    doc.Code_Id = permission_code_id
    doc.Code_Name = permission_code.name

    Story = [Spacer(1, 1.5 * inch)]

    contact_table = generate_contact_table()
    Story.append(contact_table)

    Story.append(Spacer(1, 0.5 * inch))

    job_table = generate_job_table(print_jobs)
    Story.append(job_table)

    doc.build(Story, onFirstPage=first_page, onLaterPages=other_pages)

    mark_jobs_invoiced(print_jobs)

    return doc_name
