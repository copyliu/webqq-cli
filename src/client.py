# -*- coding:utf-8 -*-

from redis import Redis
import struct
import readline

'''
1. 发送消息给朋友
2. 可自动完成朋友列表， Tab 键选择
3. 可查找朋友
4. 不写则直接发往最后选择的朋友
'''
conn = Redis()
def sendto(to, message):
    tolen, messagelen = len(to), len(message)
    bytemsg = struct.pack("iii%ss%ss" % (tolen, messagelen), 1, tolen, messagelen, to, message)
    conn.lpush("messagepool", bytemsg)


def getfriends():

    friendsinfo = conn.lrange("friends",0 ,conn.llen("friends"))
    groupsinfo = conn.lrange("groups", 0, conn.llen("groups"))

    friendsinfo.extend(groupsinfo)

    def completer(prefix, index):
        matches = [friend for friend in friendsinfo if friend.startswith(prefix)]
        try:
            return matches[index]
        except IndexError:
            pass

    readline.set_completer(completer)
    readline.parse_and_bind("tab:complete")

def chat():
    lastfriend = ""
    import colorama
    colorama.init()
    from colorama import Fore

    while 1:
        message = raw_input("|%s%s%s_>: " % (Fore.GREEN,lastfriend,Fore.RESET))
        if message =="quit":
            break
        if message =="":continue

        if " " in message:
            to, body = message.split(" ")
        else:
            to, body = lastfriend, message
        # body = message
        sendto(to,  body)

        lastfriend = to

if __name__ == '__main__':
    getfriends()
    chat()
