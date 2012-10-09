# -*- coding:utf-8 -*-

from redis import Redis
import struct
import readline
import re

'''
1. 发送消息给朋友
2. 可自动完成朋友列表， Tab 键选择
3. 可查找朋友
4. 不写则直接发往最后选择的朋友

发送数据的数据结构
+------------+------------------------+
| int32      | 消息类型               |
|            | 1. 普通消息            |
|            | 2. 窗口抖动消息        |
|            | 3. 群消息              |
|            | 4. 注销消息            | 
+============+========================+
| int32      | 消息接受者长度         |
+------------+------------------------+
| int32      | 消息正文长度           |
+------------+------------------------+
| string     | 消息接受者             |
+------------+------------------------+
| string     | 消息正文               |
+------------+------------------------+

`注意事项`:
    1. 如果消息类型为注销消息（4 ),则后续字段不填
'''
MESSAGE = 1
SHAKEMESSAGE = 2
GRPMESSAGE = 3

class Chat(object):

    def __init__(self):
        self.lastfriend = ""
        self.conn = Redis()
        self.runflag = True

    def executecmd(self, cmd, param):
        if cmd == "shake":
            self.sendto(SHAKEMESSAGE, param,'')
            self.lastfriend = param

        if cmd == "quit":
            self.runflag = False

    def parsecmd(self, message):
        cmdpattern = re.compile(r'^:(.*) ?(.*)$')
        msgpattern = re.compile(r'^(.* )?(.*)$')
        cmdmatch, msgmatch = cmdpattern.match(message), msgpattern.match(message)

        if cmdmatch:
            cmd, param = cmdmatch.groups()
            self.executecmd(cmd, param)

        elif msgmatch:
            message = msgmatch.group() 
            if not message or message =="":
                return
            to, body = msgmatch.groups()

            if not to and body:
                to = self.lastfriend
            to = to.strip()

            if to.find("_")>-1:
                self.sendto(GRPMESSAGE, to, body)    
            else:
                self.sendto(MESSAGE, to, body)    
            self.lastfriend = to

        else:
            pass
            
    def sendto(self, msgtype, to, message):
        # msgtype = 3 if to.find("_")>-1 else 1
        tolen, messagelen = len(to), len(message)
        bytemsg = ""
        if msgtype == MESSAGE or msgtype == GRPMESSAGE:
            bytemsg = struct.pack("iii%ss%ss" % (tolen, messagelen), msgtype, tolen, messagelen, to, message)
        elif msgtype == SHAKEMESSAGE:
            bytemsg = struct.pack("ii%ss" % tolen, msgtype, tolen, to)

        self.conn.lpush("messagepool", bytemsg)


    def getfriends(self):

        friendsinfo = self.conn.lrange("friends",0 ,self.conn.llen("friends"))
        groupsinfo = self.conn.lrange("groups", 0, self.conn.llen("groups"))

        friendsinfo.extend(groupsinfo)

        def completer(prefix, index):
            matches = [friend for friend in friendsinfo if friend.startswith(prefix)]
            try:
                return matches[index]
            except IndexError:
                pass

        readline.set_completer(completer)
        readline.parse_and_bind("tab:complete")
        return self

    def chat(self):
        import colorama
        colorama.init()
        from colorama import Fore

        while self.runflag:
            message = raw_input("|%s%s%s_>: " % (Fore.GREEN,self.lastfriend,Fore.RESET))
            self.parsecmd(message)
   
if __name__ == '__main__':
    Chat().getfriends().chat()
