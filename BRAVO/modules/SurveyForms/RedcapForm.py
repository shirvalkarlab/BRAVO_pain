""""""
"""
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under Open Source GPL-3.0 License

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
"""
"""
Survey Form Handling for REDCap Integration
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

import datetime
import requests 


class ReviewRequiredError(ValueError):
    """A linked raw survey is not an approved input for this participant."""


def require_approved_link(Participant, form):
    from modules.RCS08DataPolicy import applies_to
    if form.record_type == "Redcap Linked Survey" and applies_to(Participant):
        raise ReviewRequiredError(
            "This legacy REDCap link has not passed the reviewed RCS08 processing. "
            "Use the managed REDCap forms; review and import this link before analyzing it.")

def validateRedcapAPI(url, token):
    try:
        response = requests.post(url=url, data={
            "token": token,
            "format": "json",
        })
        data = response.json()
        if "error" in data:
            if data["error"] == 'The value of the parameter "content" is not valid':
                return True
        return False
        
    except Exception as e:
        print(e)
        return False

def queryRedcapFormRecords(Participant, form, recordId=None):
    require_approved_link(Participant, form)
    try:
        fields = []
        for page in form.record["FieldMapping"]:
            for question in page["questions"]:
                if question["type"] == "redcapForm":
                    fields.append(question["value"])
        
        response = requests.post(form.record["RedcapURL"], data={
            "token": form.record["RedcapToken"],
            "content": "record",
            "format": "json",
            "records": recordId,
            "fields": ','.join(fields)
        })
        data = response.json()

    except Exception as e:
        print(e)
        return []
    
    records = []
    for i in range(len(data)):
        record = {
            "Id": i,
            "Name": "",
            "Date": 0,
            "Result": [],
        }
        for page in form.record["FieldMapping"]:
            pageResult = []
            for question in page["questions"]:
                if question["type"] == "redcapForm":
                    if question["value"] in data[i]:
                        if question["text"] == "Time":
                            try:
                                record["Date"] = datetime.datetime.fromisoformat(data[i][question["value"]]).timestamp()
                            except:
                                pass
                        pageResult.append(data[i][question["value"]])
                    else:
                        pageResult.append(None)
                else:
                    pageResult.append(None)
            record["Result"].append(pageResult)
        
        if record["Date"] != 0:
            records.append(record)
            
    return records
        
