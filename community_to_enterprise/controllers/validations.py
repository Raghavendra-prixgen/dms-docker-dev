from odoo import fields, http, _
from odoo.http import request,Response
from datetime import datetime
import json
import logging
import os
from pprint import pprint

from odoo import api, models
from odoo.http import request



class API():

    

    def RemoveUnwantedKeys(arg_dict):
        #returns a copy (shallow copy) of the dictionary.
        processed_dict = arg_dict.copy()
        # example:{'Physics':67, 'Maths':87,'social':} (it will remove social key)
        for dict_key in arg_dict.keys():     
            if not arg_dict.get(dict_key):
                processed_dict.pop(dict_key)
        return processed_dict
                            #contact_fields,processed_dict,mandatory_fields
    def FieldValidation(model_fields,arguments,mandatory_fields):
        args_list = [arg_field for arg_field in arguments.keys()]
        model_field_list = [model_field for model_field in model_fields.keys()]
        for requried_field in mandatory_fields:
            #'name' and 'api' is not in args_list
            if not requried_field in args_list:
                return {'success':False,'response':{},'message':" '{tfield}' field was mandatory!".format(tfield=requried_field),'status':"403"}#403-the server understands the request but refuses to authorize it. 

        for arg_field in args_list:
            if arg_field in model_field_list:
                type_string = ['char','text','selection']
                type_integer = ['Integer','many2one']
                type_bool = ['boolean']
                type_list = ['one2many','many2many']
                type_float =['float']
                type_date = ['date']
                type_datetime=['datetime']
                if model_fields.get(arg_field).get('type') in type_string:
                    if not (type(arguments.get(arg_field)) is str):
                        return {'success':False,'response':{},'message':"The '{tfield}' field expect value in String but Received '{rtype}'".format(tfield=arg_field,rtype=type(arguments.get(arg_field)).__name__),'status':"403"}
                elif model_fields.get(arg_field).get('type') in type_integer:
                    if not (type(arguments.get(arg_field)) is int):
                        return {'success':False,'response':{},'message':"The '{tfield}' field expect value in Integer but Received '{rtype}'".format(tfield=arg_field,rtype=type(arguments.get(arg_field)).__name__),'status':"403"}
                elif model_fields.get(arg_field).get('type') in type_float:
                    if not (type(arguments.get(arg_field)) is float):
                        return {'success':False,'response':{},'message':"The '{tfield}' field expect value in Float but Received '{rtype}'".format(tfield=arg_field,rtype=type(arguments.get(arg_field)).__name__),'status':"403"}
                elif model_fields.get(arg_field).get('type') in type_bool:
                    if not (type(arguments.get(arg_field)) is bool):
                        return {'success':False,'response':{},'message':"The '{tfield}' field expect value in Boolean but Received '{rtype}'".format(tfield=arg_field,rtype=type(arguments.get(arg_field)).__name__),'status':"403"}
                elif model_fields.get(arg_field).get('type') in type_list:
                    if not (type(arguments.get(arg_field)) is list):
                        return {'success':False,'response':{},'message':"The '{tfield}' field expect value in List but Received '{rtype}'".format(tfield=arg_field,rtype=type(arguments.get(arg_field)).__name__),'status':"403"}
                
                elif model_fields.get(arg_field).get('type') in type_date:
                    try:
                        datetime.strptime(arguments.get(arg_field), '%Y-%m-%d')
                    except:
                        return {'success':False,'response':{},'message':"The '{tfield}' field 'Incorrect data format, should be YYYY-MM-DD'".format(tfield=arg_field,rtype=type(arguments.get(arg_field)).__name__),'status':"403"}

                elif model_fields.get(arg_field).get('type') in type_datetime:
                    try:
                        datetime.strptime(arguments.get(arg_field), '%Y-%m-%d %H:%M:%S')
                    except:
                        return {'success':False,'response':{},'message':"The '{tfield}' field 'Incorrect data Time format, should be YYYY-MM-DD' H:M:S".format(tfield=arg_field,rtype=type(arguments.get(arg_field)).__name__),'status':"403"}



                else:
                    return {'success':False,'response':{},'message':"The '{tfield}' field didnt match with required type!".format(tfield=arg_field),'status':"403"}

        return False
  

    def RemoveReferenceFieldNew(original_dict,unwated_list):
        processed_dict = dict(original_dict)
        list_key = processed_dict.keys()
        list_old = unwated_list.keys()
        for itm in list(list_key):
            if itm not in list(list_old):
                processed_dict.pop(itm)
        return processed_dict

    
    
    def draftpartner(var):
        return request.env['draft.partner'].sudo().search([('mobile','=',var)])

    def respartner(var):
        return request.env['res.partner'].sudo().search([('mobile','=',var)])
    
   