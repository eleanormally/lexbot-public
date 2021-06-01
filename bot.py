#created by Kiernan Olson for use at Lexington High School, MA

import firebase_admin
from firebase_admin import db
import glob
import asyncio
from os import listdir
import os
import discord
from discord.ext import tasks
from firebase_admin import credentials
import json
from cryptography.fernet import Fernet
from datetime import datetime

client = discord.Client()
taskdir = "/tmp/bottasks/"
guild = None
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

firebase_cred = credentials.Certificate('firebase.json')
firebase_admin.initialize_app(firebase_cred, {
    'databaseURL': 'https://lhsdicord.firebaseio.com'
})
ref = db.reference('/tasks')

switcher = {
    '9': 'Freshman',
    '10': 'Sophomore',
    '11': 'Junior',
    '12': 'Senior',
}

def generateKey():
    key = Fernet.generate_key()
    with open('key.secret', 'wb') as key_file:
        key_file.write(key)

def generateToken(dtag):
    key = open("key.secret", "rb").read()
    now = datetime.now()
    timekey = now.strftime("%m:%d:%H")
    out = str(dtag) + ' ' + timekey
    out = out.encode()
    f = Fernet(key)
    encrypted = f.encrypt(out).decode()
    return encrypted

def checkToken(token, dtag):
    token = token.encode()
    key = open('key.secret', 'rb').read()
    now = datetime.now()
    f = Fernet(key)
    decrypted = f.decrypt(token).decode().split()
    checktag = decrypted[0]
    timekey = decrypted[1].split(':')
    timekey = [int(x) for x in timekey]
    if (checktag == dtag and timekey[0] == now.month and timekey[1] == now.day and (timekey[2]-now.hour)%22 <= 1):
        return True
    else:
        return False

@client.event
async def on_ready():
    global guild
    print('logged in as {0.user}'.format(client))
    guild = client.guilds[0]
    if (not os.path.exists("key.secret")):
        generateKey()
        print("key generated")

@client.event
async def on_member_join(member):
    await member.send("Welcome to the LHS Discord Server! To get access to all your class, grade, and school chats please enter your school email:")

@client.event
async def on_message(message):
    s = smtplib.SMTP(host='smtp.gmail.com',port=587)
    s.starttls()
    smtpuname = ''
    smtppwd = ''
    with open('email.secret', 'r') as f:
        smtpuname = f.readline()
        smtppwd = f.readline()
        s.login(smtpuname, smtppwd)
    if (message.guild is None and not message.author.bot):
        if(not message.content.endswith('@lexingtonma.org') or not message.content.startswith('2')):
            await message.author.send("not a valid LHS email")

        msg = MIMEMultipart()
        msg['From'] = smtpuname
        msg['To'] = message.content
        msg['Subject'] = 'Login to LHS Discord'

        msg.attach(MIMEText(u'<a href="https://lexbot.mynt.pw/?dtag=' + str(message.author.id) + '&token=' + generateToken(message.author.id) + '">Click here to select your classes and sign into the LHS Discord</a>', 'html'))
        s.send_message(msg)
        await message.author.send("a link has been sent to your email. if you mistyped your email just enter it again.")
        del msg
    elif message.content.startswith('%email'):
        addr = message.content.split()[1]
        if(not addr.endswith('@lexingtonma.org') or not addr.startswith('2')):
            await message.channel.send("not a valid LHS email")
            return
        msg = MIMEMultipart()
        msg['From'] = smtpuname
        msg['To'] = addr
        msg['Subject'] = 'Login to LHS Discord'

        msg.attach(MIMEText(u'<a href="https://lexbot.mynt.pw/?dtag=' + str(message.author.id) + '&token=' + generateToken(message.author.id) +'">Click here to select your classes and sign into the LHS Discord</a>', 'html'))
        s.send_message(msg)
        await message.author.send("a link has been sent to your email. if you mistyped your email just enter it again.")
async def create_class_group(cname, group, user):
    if(len(cname) == 8 and cname[4] == '-'):
        return
    global guild
    role = await guild.create_role(name=cname)

def not_mod(m):
    return m.content.startswith('====') == False

def processClasses(classes):
    with open('keywords.json') as f:
        keywords = json.load(f)
    cont = False
    found = False
    proc = []
    for c in classes:
        for d in keywords.keys():
            for key in keywords[d]:
                if key in c.lower():
                    if d != 'gym':
                        proc.append([c, d])
                    cont = True
                    break
            if cont:
                break
        if cont:
            cont = False
        else:
            proc.append([c, 'other'])
    return proc

@tasks.loop(seconds=20)
async def bifuf():
    global guild
    if not guild:
        return
    await client.wait_until_ready()
    try:
        dbtasks = ref.order_by_key().get()
    except:
        print("db ref error")
        return
    if not dbtasks:
        return
    tasks = []
    for key, val in dbtasks.items():
        tasks.append([val, key])
    for task in tasks:
        key = task[1]
        task = task[0]
        roleList = []
        user = None
        try:
            user = await guild.fetch_member(int(task['dtag']))
        except:
            print("user " + task['dtag'] + " no longer in server, deleting")
            delreq = db.reference('/tasks/' + key)
            delreq.delete()
            continue
        if(not user):
            print("user " + task['dtag'] + " not found")
            delreq = db.reference('/tasks/' + key)
            delreq.delete()
            continue
        if(checkToken(task['token'], task['dtag']) == False):
            print("token error for user " + user.name)
            delreq = db.reference('/tasks/' + key)
            delreq.delete()
            continue
        await user.edit(nick=task['name'])
        await user.add_roles(discord.utils.get(guild.roles, name='Member'))
        gradeswitch = switcher.get(task['grade'])
        await user.add_roles(discord.utils.get(guild.roles, name=gradeswitch))
        roles = []
        try:
            roles = processClasses(task['roles'])
        except:
            print("role error for " + task['dtag'])
            delreq = db.reference('/tasks/' + key)
            delreq.delete()
            continue
        for role in roles:
            group = role[1]
            role = role[0]
            roleref = discord.utils.get(guild.roles, name=role)
            if roleref:
                r = await user.add_roles(roleref)
            elif role:
                group = group[1]
                await create_class_group(role, group, user)
        print("added " + user.name)
        delreq = db.reference('/tasks/' + key)
        delreq.delete()
        await guild.get_channel(755430754506375300).purge(limit=100, check=not_mod)


bifuf.start()
with open('token.secret','r') as f:
    client.run(f.read())
