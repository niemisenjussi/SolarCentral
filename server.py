#!/usr/bin/env python
# -*- coding: utf-8 -*-
from flask import Flask
from flask import Response
from flask import send_file
import json
import psycopg2
import os
import setproctitle
import requests

app = Flask(__name__)

#database = ""


def connect_db():
    conn = psycopg2.connect("host='localhost' dbname='solar' user='solarslave' password='solarslave'")
    return conn

def disconnect_db(conn):
    conn.close()

def get_live():
    target = []
    try:
        fh = open('/mnt/ramdisk/liveinfo.txt')
        data = fh.read()
        data = data.replace('\n','').replace('\r','')
        row = data.split(';')
        target = [
                [u'Jännite',str(row[0])+'V'],
                ['Virta',str(float(row[1]))+'mA'],
                ['Teho',row[2]+'W'],
                ['PWM 1',row[3]],
                ['PWM 2',row[4]],
                ['PWM 3',row[5]],
                [u'MOSFET 1 lämpö',row[6]+" &#8451;"],
                [u'MOSFET 2 lämpö',row[7]+" &#8451;"],
                [u'MOSFET 3 lämpö',row[8]+" &#8451;"],
                ['Tila',row[9]]
        ]
    except:
        target = [
                [u'Jännite','0V'],
                ['Virta','0mA'],
                ['Teho','0W'],
                ['PWM 1','0'],
                ['PWM 2','0'],
                ['PWM 3','0'],
                [u'MOSFET 1 lämpö','0'],
                [u'MOSFET 2 lämpö','0'],
                [u'MOSFET 3 lämpö','0'],
                ['Tila','0']
        ]
    return json.dumps(target)

def get_monthly_stats():
    query = """select
                extract('year' from "PERIOD_START_TIME"::timestamp with time zone),
                extract('month' from "PERIOD_START_TIME"::timestamp with time zone),
                sum("POWER")*24
            from
                {TABLE}
            where
                "PERIOD_START_TIME" >= current_timestamp - interval '12 month'
            group by
                extract('year' from "PERIOD_START_TIME"::timestamp with time zone),
                extract('month' from "PERIOD_START_TIME"::timestamp with time zone)
            order by
                1,2 asc"""
    
    database = connect_db()
    query = query.format(TABLE = '"POWER_USAGE_DAY"')

    cursor = database.cursor()
    cursor.execute(query)
    result = cursor.fetchall()

    target = [{'key':u'Energia (kWh)', 'values':[],'bar':True}]  
    for row in result:
        target[0]['values'].append([row[0], row[1], row[2]])


    cursor.close() 
    disconnect_db(database)
    return json.dumps(target)


def exec_query(parameter, level, days):
    query = """    
        select
            extract('epoch' from "PERIOD_START_TIME"::timestamp with time zone),
            extract('day' from "PERIOD_START_TIME"::timestamp with time zone),
            "VOLTAGE",
            "CURRENT",
            "POWER",
            "TEMP1",
            "TEMP2",
            "TEMP3",
            "PWM_R1"+"PWM_R2"+"PWM_R3"
        from
           {TABLE}
        where
            "PERIOD_START_TIME" >= current_timestamp - interval '{DAY}'
        order by
            1 asc"""

    table = "POWER_USAGE_DAY"
    timelevel = '2 day'
    cumulativedivisor = 1 # scale selected data for cumulative energy calculation

    if level == 'day':
        table = '"POWER_USAGE_DAY"'
        timelevel = str(days)+' min'
        cumulativedivisor = 1.0/24.0
        if parameter == 'plainenergy':
            timelevel = '30 day'    
            cumulativedivisor = 1.0/24
    elif level == 'hour':
        table = '"POWER_USAGE_HOUR"'
        timelevel = str(days)+' min'
        cumulativedivisor = 1.0
    elif level == '15min':
        table = '"POWER_USAGE_15MIN"'
        timelevel = str(days)+' min'
        cumulativedivisor = 4.0
    elif level == 'min':
        table = '"POWER_USAGE_MIN"'
        timelevel = str(days)+' min'
        cumulativedivisor = 60.0
    elif level == 'sec':
        table = '"POWER_USAGE_SEC"'
        timelevel = str(days)+' min'
        cumulativedivisor = 3600.0
        print "SEC table select"
        #print query

    print timelevel, table, cumulativedivisor
    database = connect_db()
    query = query.format(TABLE = table, DAY = timelevel)

    cursor = database.cursor()
    cursor.execute(query)
    result = cursor.fetchall()
    target = []
    if parameter == 'energy':
        target = [{'key':u'Energia (kWh)', 'values':[],'bar':True},
                  {'key':u'Jännite (V)', 'values':[], 'bar':False},
                  {'key':u'Virta (A)', 'values':[], 'bar':True},
                  {'key':u'Teho (W)', 'values':[], 'bar':True},
                  {'key':'Kuorma (R)', 'values':[],'bar':False},
                  {'key':u'MOSFET1 Temp', 'values':[],'bar':False},
                  {'key':u'MOSFET2 Temp', 'values':[],'bar':False},
                  {'key':u'MOSFET3 Temp', 'values':[],'bar':False},

                  ]
        current_day = -1
        cumsum = 0
        for row in result:
            if current_day == -1:
                current_day = row[1]
            elif current_day != row[1]: #date has changed
                cumsum = 0
                current_day = row[1]
            if level == "day":
                target[0]['values'].append([row[0]*1000, row[4]*24/1000])
            else:
                target[0]['values'].append([row[0]*1000, cumsum/1000])
            target[1]['values'].append([row[0]*1000, row[2]])
            target[2]['values'].append([row[0]*1000, row[3]/1000])
            target[3]['values'].append([row[0]*1000, row[4]])
            target[4]['values'].append([row[0]*1000,row[8]])
            target[5]['values'].append([row[0]*1000,row[5]])
            target[6]['values'].append([row[0]*1000,row[6]])
            target[7]['values'].append([row[0]*1000,row[7]])

            cumsum += row[4]/cumulativedivisor
   
    elif parameter == 'plainenergy':
        target = [{'key':u'Energia (kWh)', 'values':[],'bar':True}]  
        for row in result:
            target[0]['values'].append([row[0]*1000,float(row[4]/cumulativedivisor)/1000.0])

    elif parameter == 'voltcur':
        target = [  {'key':u'Jännite (V)', 'values':[], 'bar':False, 'yAxis':2},
                    {'key':u'Virta (A)', 'values':[], 'bar':True, 'yAxis':1}]
        for row in result:
            target[0]['values'].append([row[0]*1000,row[2]])
            target[1]['values'].append([row[0]*1000,row[3]/1000])

    elif parameter == 'power':
        target = [{'key':'Teho (W)', 'values':[],'bar':True, 'yAxis':1},
                  {'key':'Kuorma (R)', 'values':[],'yAxis':2}] #8
        for row in result:
            target[0]['values'].append([row[0]*1000,row[4]])
            target[1]['values'].append([row[0]*1000,row[8]])

    cursor.close() 
    disconnect_db(database)
    return json.dumps(target)

def read_file(filename):
    with open(filename, 'r') as fh:
        data = fh.read()
        return data
    return ""

@app.route("/getdata/<parameter>/<level>/<timelevel>")
def getdata(parameter, level, timelevel):
    resp = Response(response = exec_query(parameter, level, timelevel),
                    status = 200,
                    mimetype = "application/json")
    return resp

@app.route("/monthly")
def monthly():
    resp = Response(response = get_monthly_stats(), status = 200, mimetype = 'application/json')
    return resp


@app.route("/getlive")
def livedata():
    resp = Response(response = get_live(),
                    status = 200,
                    mimetype = "application/json")
    return resp


@app.route("/camera")
def camera():
    resp = Response(response = requests.get("http://192.168.1.19/html/cam_pic.php?time=12345&pDelay=1"),
                    status = 200,
                    mimetype = "image/jpeg")
    return resp

@app.route("/build/<filename>")
def getfile(filename):
    content_types = {'.js':'application/x-javascript', '.css':'text/css'}
    conttype = 'text/html'
    for t in content_types:
        if filename.endswith(t):
            conttype = content_types[t]
    resp = Response(response = read_file('build/'+str(filename)),
                    status = 200,
                    mimetype = conttype)
    return resp

@app.route("/stylesheets/<filename>")
def getstyle(filename):
    conttype = 'text/css'
    resp = Response(response = read_file('stylesheets/'+str(filename)),
                    status = 200,
                    mimetype = conttype)
    return resp

@app.route('/images/<image>')
def get_image(image):
    return send_file('images/'+image, mimetype='image/jpg')



@app.route("/<filename>")
def getrootfile(filename):
    content_types = {'.js':'application/x-javascript', '.css':'text/css'}
    conttype = 'text/html'
    for t in content_types:
        if filename.endswith(t):
            conttype = content_types[t]
    resp = Response(response = read_file(str(filename)),
                    status = 200,
                    mimetype = conttype)
    return resp

@app.route("/")
def index():
    resp = Response(response = read_file('index.html'),
                    status = 200,
                    mimetype = "text/html")
    return resp

if __name__ == "__main__":
    setproctitle.setproctitle("solarcentral")
    #database = connect_db()
    #cursor = database.cursor()

    #app.debug = True
    app.run(host='0.0.0.0', port=10000, threaded=True) 

