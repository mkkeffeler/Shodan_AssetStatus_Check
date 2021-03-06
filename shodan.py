#!/az/arcsight/counteract_scripts/env/bin/python
__author__ = "mkkeffeler"
#Script that gets provided list of zones to check against Shodan
#On first run, it will run all IPs and save them in a CSV file, no events generated
#Subsequently, it will check that file and requery all IPs in the zone and compare to determine changes.
#Any changes that are made, get updated in the CSV file and generate a cef event as shown on line 164
#Usage: python shodan.py (no parameters can be provided at this point)
#Future updates: This is somewhat memory intensive, we could save the data of an IP address individually
#rather than doing them all, and saving at the end. 
#Future Update 2: Move api key to config file or find another way to store potentially multiple.

import requests
import sys
import ipaddress
from configparser import ConfigParser
import dateutil.parser
from pprint import pprint
from netaddr import *
import json
import os
import time
import csv
from tempfile import NamedTemporaryFile
import shutil
from submit_event import generate_cef_event,generate_cef_event_arcsight_list,which_field,syslog
import cef_event

api_key = 'fgKrboZtuq3I8KHuw5Fk4r9KTeNXa3xZ'#Might be best to have 2-3 keys here if we are doing lots of zones

def Port_list(shodan):
    message = ""
    for port in shodan['ports']:
       message += str(port) + " "
    if (message == ""):
        return "No Historical Port Information."
    else:
        return message
def Vuln_list(shodan):
    print("VULN LIST")
    message = ""
    if "vulns" in shodan["data"][0].keys():
        for vuln in shodan['data'][0]['vulns']:
           message += str(vuln) + " "
        if (message == ""):
            return "No Vulnerability Information."
        else:
            return message
    else:
        return "N/A"
def hostname_list(shodan):
    message = ""
    for hostname in shodan['hostnames']:
       message += str(hostname) + " "
    if (message == ""):
        return "No Historical Hostname Information."
    else:
        return message
def certificate_status(shodan):
    message = ""
    if "ssl" in shodan.keys():
        if "cert" in shodan['ssl'].keys():
            return "Certificate Expired: " + str(shodan['ssl']['cert']['expired'])
    else:
        return "Certificate Unknown."

def check_org(shodan):
    message = ""
    if "org" in shodan.keys():
        return str(shodan['org'])
    else:
        return "No Organization Listed"

def check_time(shodan):
    message = ""
    if "timestamp" in shodan['data'][0].keys():
        return str(dateutil.parser.parse(str(shodan['data'][0]['timestamp'])).strftime("%x"))
    else:
        return "No Updated Time Available."

def check_asn(shodan):
    message = ""
    if "asn" in shodan.keys():
        return str(shodan['asn'])
    else:
        return "No ASN Provided."

def domain_list(shodan):
    message = ""
    for domain in shodan:
        message += str(domain) + " "
    if (message == ""):
        return "No Historical Domain Name Information."
    else:
        return message
def warn_and_exit(msg):
    print('Error:')
    print(msg)
    exit()

def is_private_or_null(ip):  #Offloaded this function
    try:
        parsed_ip = ipaddress.ip_address(ip)
        if parsed_ip.is_private:
            return 1
        else:
            return 0
    except Exception as ex:
        warn_and_exit(str(ex))
    if ip == "":
        warn_and_exit("There was no IP address provided on execution")
#This function can be passed a filename and will open the csv file with information on that zone
#Then will load it into a dictionary for our use and pass the dict back
def zone_file_to_dict(zone):

    zone_info = {}
    parts = zone.split(".")
    last = parts[3].split("/")[0]
    if os.path.isfile(parts[0]+parts[1]+parts[2]+last+".csv"):
        ifile = open(parts[0]+parts[1]+parts[2]+last+".csv","r")
        file = csv.reader(ifile)
        for line in file:
          #  print line
            zone_info[line[0]] = {}
            zone_info[line[0]]["location"] = line[5]
            zone_info[line[0]]["certificate"] = line[2]
            zone_info[line[0]]["ports"] = line[4]
            zone_info[line[0]]["organization"] = line[6]
            zone_info[line[0]]["domain"] = line[1]
            zone_info[line[0]]["ASN"] = line[7]
            zone_info[line[0]]["hostname"] = line[3]
            zone_info[line[0]]["version"] = line[8]
            zone_info[line[0]]["vulns"] = line[9]

    return zone_info
#This function takes a dictionary, and writes it out to a zone file in CSV format
def dict_to_zone_file(order,zonedict,zone):
    ordered = ["domain","certificate","hostname","ports","location","organization","ASN","version","vulns"]
    cur_details = []
    parts = zone.split(".")
    last = parts[3].split("/")[0]
    file = open(parts[0]+parts[1]+parts[2]+last+".csv","w")
    writer = csv.writer(file, delimiter=',',quoting=csv.QUOTE_ALL)
    for ip in order:
        print (zonedict[ip])
        line = [ip]
        for detail in ordered: #for every element in this row
            line.append(zonedict[ip][detail]) #Now append new data in where it should be
        writer.writerow(line)
#Used to update the csv zone file, and report that there was a change to the zone file
def split_ip(ip):
    """Split a IP address given as string into a 4-tuple of integers."""
    return tuple(int(part) for part in ip.split('.'))

def my_key(item):
    return split_ip(item[0])
def update_and_report(zonelength,ip,zone,linenumber,key_changed,newdata,olddata,updatedindex,ipdata):
    print ("WE IN HERE - Update and Report")
    ordered = ["domain","certificate","hostname","ports","location","organization","ASN","version","vulns"]
    ipdata = json.loads(ipdata)
    row_count = zonelength
    parts = zone.split(".")
    last = parts[3].split("/")[0]
    filename = parts[0]+parts[1]+parts[2]+last+".csv"
    linecount = 0
    reader = csv.reader(open(filename,"r"), delimiter=',')
    writer = csv.writer(open("holder.txt","w"), delimiter=',')
    # row_count = sum(1 for row in reader) # fileObject is your csv.reader
     #   print str((row_count - linenumber))
    for row in reader:
        #    print "ROWSSSS"
        if linecount != (linenumber):  #If the row we are looking at is not the one we need to update
            writer.writerow(row)
            print ("FOUND THE LINE")
            linecount += 1
        else: #Now we have the row we need to edit
            print ((row))
            line = []
            index = 0
            for detail in row: #for every element in this row
                if index != updatedindex: #If this element is not at the index of the one to be updated, write it to list
                    line.append( detail )
                    index += 1
                else:
                    line.append(newdata) #Now append new data in where it should be
                    index += 1
            writer.writerow(line) #Write the row
            linecount += 1
    shutil.move("holder.txt", filename) #Move temp file to permanent, don't want to read and write to same file
    print (ipdata)
    ipdata[ordered[updatedindex-1]] = newdata
    print(ipdata)
    if key_changed == "vulns":
        vulnnew = ""
        upordown = 0
        if len(newdata.split(" ")) > len(olddata.split(" ")):
            upordown = 1
            for item in newdata.split(" "):
                if item not in olddata.split(" "):
                    vulnnew += item + " "

        else:
            upordown = -1
            for item in olddata.split(" "):
                if item not in newdata.split(" "):
                    vulnnew += item + " "

        
        event = generate_cef_event(key_changed,vulnnew,olddata,ip,upordown,json.dumps(ipdata),ordered) #Generate a cef event for this change
    else:
        event = generate_cef_event(key_changed,newdata,olddata,ip,0,json.dumps(ipdata),ordered)
    print (event)
    syslog(event)
    return
def check_version(shodan):
    if "title" in shodan["data"][0].keys():
        return shodan["data"][0]["title"]
    else:
        return "N/A"
if __name__ == "__main__":
    config = ConfigParser()
    config.read('config.ini')
    config_zones = config.get('DEFAULT','zones')
    config_zones = config_zones.split(",")
    zones = config_zones
    order = []
   #List of zones to be checked
    for zone in zones:  #for every zone
        linenumber = 0
        order = []
        previousstate = zone_file_to_dict(zone) #Check if we have done this zone before, if so load up the previous results
        if previousstate != {}: #If we have done this zone once before, then we should check everything. 
            for ip in IPNetwork(zone): #For all IPs in this zone
                zonelength = len(IPNetwork(zone))
                order.append(str(ip))
                if (is_private_or_null(ip) == 0):  #If its private or empty, seems useless to check
                    parsed_ip = ip
                    time.sleep(1) #Can't check against Shodan more than 1 time per second
                    response = requests.get('https://api.shodan.io/shodan/host/%s?key=%s' % (str(parsed_ip), api_key))
                    print ("IP: " + str(parsed_ip))
                    shodan= response.json()
                   # print ("we ready")
                    if 'data' in shodan.keys(): #if we got data back, check that it doesn't conflict
                    #    print ("first: " + str(previousstate[str(ip)]["hostname"]))
                     #   print ("second: " + str(hostname_list(shodan).split(" ")))
                        if (str(shodan['data'][0]['location']['country_name']) != previousstate[str(ip)]["location"]):
                            update_and_report(zonelength,str(ip),zone,linenumber,"location",str(shodan['data'][0]['location']['country_name']),previousstate[str(ip)]["location"],5,json.dumps(previousstate[str(ip)]))
                          #  event = generate_cef_event_arcsight_list("location",str(ip), str(shodan['data'][0]['location']['country_name']))#Generate a cef event for this change
                           # print (event)
                           # syslog(event)
                        if sorted(hostname_list(shodan).split(" ")) != sorted(previousstate[str(ip)]["hostname"].split(" ")):
                            update_and_report(zonelength,str(ip),zone,linenumber,"hostname",hostname_list(shodan),previousstate[str(ip)]["hostname"],3,json.dumps(previousstate[str(ip)]))
                           # event = generate_cef_event_arcsight_list("hostname",str(ip),hostname_list(shodan)) #Generate a cef event for this change
                           # print (event)
                           # syslog(event)
                        domains = domain_list(shodan['data'][0]['domains']).split(" ")
                        if sorted(previousstate[str(ip)]["domain"].split(" ")) != sorted(domains):
                            update_and_report(zonelength,str(ip),zone,linenumber,"domain",domain_list(shodan['data'][0]['domains']),previousstate[str(ip)]["domain"],1,json.dumps(previousstate[str(ip)]))
                           # event = generate_cef_event_arcsight_list("domain",str(ip),domain_list(shodan['data'][0]['domains'])) #Generate a cef event for this change
                           # print (event)
                           # syslog(event)
 
                        if certificate_status(shodan['data'][0]) != previousstate[str(ip)]["certificate"]:
                            update_and_report(zonelength,str(ip),zone,linenumber,"certificate",certificate_status(shodan['data'][0]),previousstate[str(ip)]["certificate"],2,json.dumps(previousstate[str(ip)]))
                           # event = generate_cef_event_arcsight_list("certificate",str(ip),certificate_status(shodan['data'][0])) #Generate a cef event for this change
                           # print (event)
                           # syslog(event)
 
                        if check_asn(shodan) != previousstate[str(ip)]["ASN"]: 
                           # print "1: " + check_asn(shodan) + "2 " + previousstate[str(ip)]["asn"]
                            update_and_report(zonelength,str(ip),zone,linenumber,"ASN",check_asn(shodan),previousstate[str(ip)]["ASN"],7,json.dumps(previousstate[str(ip)]))
                           # event = generate_cef_event_arcsight_list("ASN",str(ip),check_asn(shodan)) #Generate a cef event for this change
                           # print (event)
                           # syslog(event)
                        if check_org(shodan) != previousstate[str(ip)]["organization"]:
                            update_and_report(zonelength,str(ip),zone,linenumber,"organization",check_org(shodan),previousstate[str(ip)]["organization"],6,json.dumps(previousstate[str(ip)]))
                           # event = generate_cef_event_arcsight_list("organization",str(ip),check_org(shodan)) #Generate a cef event for this change
                           # print (event)
                           # syslog(event)
                        ports = Port_list(shodan).split(" ")
                        if sorted(previousstate[str(ip)]["ports"].split(" ")) != sorted(ports):
                            update_and_report(zonelength,str(ip),zone,linenumber,"ports",Port_list(shodan),previousstate[str(ip)]["ports"],4,json.dumps(previousstate[str(ip)]))
                            #event = generate_cef_event_arcsight_list("ports",str(ip),Port_list(shodan)) #Generate a cef event for this change
                            #print (event)
                            #syslog(event)
                        if previousstate[str(ip)]["version"] != check_version(shodan):
                           update_and_report(zonelength,str(ip),zone,linenumber,"version",check_version(shodan),previousstate[str(ip)]["version"],8,json.dumps(previousstate[str(ip)]))
                           # event = generate_cef_event_arcsight_list("version",str(ip),check_version(shodan)) #Generate a cef event for this change
                           # print (event)
                           # syslog(event)
                        vulns = Vuln_list(shodan).split(" ")
                        print("DOWN HERE")
                        if sorted(previousstate[str(ip)]["vulns"].split(" ")) != sorted(vulns):
                            print ("WE INSIDE TRHE IF")
                            update_and_report(zonelength,str(ip),zone,linenumber,"vulns",Vuln_list(shodan),previousstate[str(ip)]["vulns"],9,json.dumps(previousstate[str(ip)]))
                           # event = generate_cef_event_arcsight_list("vulns",str(ip),Vuln_list(shodan)) #Generate a cef event for this change
                           # print (event)
                           # syslog(event)
                    else: #otherwise it was an empty results or we had some other error, no reports should be made
                        print ("error")
                        print(shodan['error'])
                    linenumber += 1
        else: #Otherwise, lets just store everything the first time so we can set a base case
            new_baseline = {}
            for ip in IPNetwork(zone):
                    order.append(str(ip))
                    if (is_private_or_null(ip) == 0):
                        time.sleep(1)
                        parsed_ip = ip
                        response = requests.get('https://api.shodan.io/shodan/host/%s?key=%s' % (str(parsed_ip), api_key))
                        print ("IP: " + str(parsed_ip))
                        new_baseline[str(ip)] = {}
                        try:
                            shodan= response.json()
                            if 'data' in shodan.keys(): #Fill in all the info and continue
                                print ("IN HERE")
                                new_baseline[str(ip)]["location"] = str(shodan['data'][0]['location']['country_name'])
                                new_baseline[str(ip)]["hostname"] = hostname_list(shodan) 
                                new_baseline[str(ip)]["domain"] = domain_list(shodan['data'][0]['domains'])
                                new_baseline[str(ip)]["certificate"] = certificate_status(shodan['data'][0])
                                new_baseline[str(ip)]["ASN"] = check_asn(shodan)
                                new_baseline[str(ip)]["organization"] = check_org(shodan)
                                new_baseline[str(ip)]["ports"] = Port_list(shodan)
                                new_baseline[str(ip)]["vulns"] = Vuln_list(shodan)
                                try:
                                    new_baseline[str(ip)]["version"] = str(shodan["data"][0]["title"])
                                except Exception as e:
                                    ordered = ["domain","certificate","hostname","ports","location","organization","ASN","version","vulns"]
                                    new_baseline[str(ip)]["version"] = "N/A"
                                ordered = ["domain","certificate","hostname","ports","location","organization","ASN","version","vulns"]
                                print ("INSIDE")
                                event = generate_cef_event_arcsight_list(ip,ordered,json.dumps(new_baseline[str(ip)])) #Generate a cef event for this change
                                print (event)
                                syslog(event)
                             #   print (str(ip) + " " + str(new_baseline[str(ip)]))
                            else: #If this IP does not have info on it fill in N/A
                                print(shodan['error'])
                                new_baseline[str(ip)]["location"] = "N/A"
                                new_baseline[str(ip)]["hostname"] = "N/A"
                                new_baseline[str(ip)]["domain"] = "N/A"
                                new_baseline[str(ip)]["certificate"] = "N/A"
                                new_baseline[str(ip)]["ASN"] = "N/A"
                                new_baseline[str(ip)]["organization"] = "N/A"
                                new_baseline[str(ip)]["ports"] = "N/A"
                                new_baseline[str(ip)]["version"] = "N/A"
                                new_baseline[str(ip)]["vulns"] = "N/A"
                        except:
                            continue
        dict_to_zone_file(order,new_baseline,zone) #Write this to the file
