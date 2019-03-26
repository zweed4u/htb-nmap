#!/usr/bin/python3
import os
import re
import requests
import threading
import subprocess
import configparser

from bs4 import BeautifulSoup

# check if we're root
if os.geteuid() != 0:
    raise Exception("This script must be run as root!")

def get_gateway(interface):
    ip_route = subprocess.Popen(["ip", "route"], stdout=subprocess.PIPE).communicate()[0].decode()
    for line in ip_route.splitlines():
        if interface in line:
            gateway = re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', line.split('via')[-1]).group()
            return gateway
    raise Exception(f'Unable to find gateway on {interface}')

def is_vpn_connected():
    host = get_gateway('tun0')
    ping = subprocess.Popen(["ping", "-n", "1", "-w", "1", host], stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode()
    return not(('unreachable' in str(ping)) or ('timed' in str(ping)) or ('failure' in str(ping)))

assert is_vpn_connected() is True, 'Could not ping VPN gateway - are you connected to the vpn?'

root_directory = os.getcwd()
cfg = configparser.ConfigParser()
configFilePath = os.path.join(root_directory, 'config.cfg')
cfg.read(configFilePath)

username_email = cfg.get('authentication', 'username_email')
password = cfg.get('authentication', 'password')

session = requests.session()

### login ###
print('Navigating to login page to scrape token')
login_url = 'https://www.hackthebox.eu/login'
response = session.get(login_url)
response.raise_for_status() 

# scrape for _token
soup = BeautifulSoup(response.content, 'html.parser')
try:
    token = soup.findAll('input', {'name':'_token'})[0]['value']
    print('Token found!')
except:
    raise Exception('Unable to scrape login page for token')

login_payload = {
    '_token': token,
    'email': username_email,
    'password': password
}
print('Logging in...')
response = session.post(login_url, data=login_payload)
response.raise_for_status()
assert '/home' in response.url, '/home was not found in url - assuming login failed!'


### get list of machines ###
print('Navigating to active machines list')
active_machines_url = 'https://www.hackthebox.eu/home/machines/list'
response = session.get(active_machines_url)
response.raise_for_status() 

# scrape table
soup = BeautifulSoup(response.content, 'html.parser')
try:
    table = soup.findAll('table', {'id':'machinesTable'})[0]
except:
    raise Exception('Unable to find machinesTable')
try:
    tbody = table.findAll('tbody')[0]
except:
    raise Exception('Unable to find table body')

def make_dir_and_nmap(name_of_box, ip_of_box):
    try:
        os.mkdir(name_of_box)  # current_dir/name_of_box
    except:
        pass
    nmap_proc = subprocess.Popen(['sudo', 'nmap', '-sC', '-sV', '-oA', f'{name_of_box}/{name_of_box}', ip_of_box])
    nmap_proc.wait()

# parse table and pretty print
# name || maker || os || ip address || difficulty || ratings || owns || last reset || user fist blood || root first blood || availabilty || operations
print("{}{:15s} || {:7s} || {:12s} || {:10s}".format('\n', 'Box Name', 'Box OS', 'Box IP', 'Last Reset'))
print('='*(15+7+12+10 + 4+4+4))
threads = []
for tr in tbody.findAll('tr'):
    box_name = tr.findAll('td')[0].text.strip()
    maker_name = tr.findAll('td')[1].text.strip()
    box_os = tr.findAll('td')[2].text.strip()
    box_ip = tr.findAll('td')[3].text.strip()
    last_reset = tr.findAll('td')[7].text.strip()
    print("{:15s} || {:7s} || {:12s} || {:10s}".format(box_name, box_os, box_ip, last_reset))

    t = threading.Thread(target=make_dir_and_nmap, args=(box_name, box_ip))
    threads.append(t)

for t in threads:
    t.start()
for t in threads:
    t.join()
