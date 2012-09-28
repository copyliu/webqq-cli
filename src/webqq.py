# -*- coding:utf-8 -*-

import urllib, urllib2, cookielib
import json, time, os
from urllib2 import BaseHandler
import random
from hashlib import md5

import logging,logging.config

from colorama import init
init()
from colorama import Fore

import gevent, greenlet
from gevent import monkey, queue, pool
import socket
import struct

monkey.patch_all()


def getLogger():
    logging.config.fileConfig(os.path.join(os.getcwd(),"chatloggin.conf"))
    return logging.getLogger()

def textoutput(msgtype, messagetext):
    import re
    highlightre = re.match('.+ \[(.+)\](.+)', messagetext)
    if highlightre:
        who, message = highlightre.groups()[0], highlightre.groups()[1]

        if msgtype == 1:
            getLogger().info(Fore.GREEN + who + Fore.YELLOW+ message + Fore.RESET)

        if msgtype == 2:
            getLogger().info(Fore.BLUE + who + Fore.RESET + message)
        if msgtype == 3:
           getLogger().info(Fore.RED + who + Fore.RESET + message)

    else:
        getLogger().info(messagetext)


class MsgCounter(object):
    def __init__(self):
        self.msgindex = random.randint(1,99999999)

    def get(self):
        self.msgindex+=1
        return self.msgindex

MessageIndex = MsgCounter()

class WebqqHandler(BaseHandler):

    def http_request(self, request):
        request.add_header("Referer","http://d.web2.qq.com/proxy.html?v=20110331002&callback=2")
        return request

class WebQQException(Exception):pass
class MessageHandner(object):
    '''
    对消息进行处理
    '''
    pass

class QQMessage(object):

    def __init__(self, to, messagetext, context=None):
        self.msgtype = 1
        self.to = to 
        self.messagetext = messagetext.encode("utf-8")
        self.retrycount = 0
        self.context = context
    
    def encode(self, clientid, psessionid):
        self.clientid = clientid
        self.psessionid = psessionid
        r=json.dumps({"to":self.to,"face":570,"content":"[\""+self.messagetext+"\\n\",[\"font\",{\"name\":\"宋体\",\"size\":\"10\",\"style\":[0,0,0],\"color\":\"000000\"}]]","msg_id":MessageIndex.get(),"clientid":self.clientid,"psessionid":self.psessionid})
        return "r="+urllib.quote(r)+"&clientid="+self.clientid+"&psessionid="+self.psessionid

    def decode(self):
        return self.to, self.messagetext

    def sendOk(self, result):
        pass

    def sendFailed(self, result):
        try:
            result.get()
        except Exception:
            print "send %s failed" % str(self)

        if self.retrycount <3:
            self.context.write_message(self)
            self.retrycount+=1
        elif self.retrycount==3:
            print str(self), "发送失败"


    def send(self, context, clientid, psessionid):
        qqrawmsg = self.encode(clientid, psessionid)
        return context.spawn("https://d.web2.qq.com/channel/send_buddy_msg2", \
                qqrawmsg,
                task = context.sendpost,
                linkok = self.sendOk,
                linkfailed = self.sendFailed)

    def __str__(self):
        
        return "send qq message to %s, message = %s\n" % (self.to, self.messagetext)

class ShakeMessage(QQMessage):
    '''
    发送窗口抖动消息
    '''
    def __init__(self, to):
        self.msgtype = 2
        self.to = to
        self.retrycount = 0
   
    def sendFailed(self, *args):
        print "shake message send failed!"

    def send(self, context, clientid, psessionid):
        url = "http://d.web2.qq.com/channel/shake2?to_uin="+str(self.to)+"&clientid="+clientid+"&psessionid="+psessionid+"&t="+str(time.time())
        return context.spawn(url, 
                task = context.sendget, 
                linkfailed = self.sendFailed)

    def __str__(self):
        return "send shake message to %s" % self.to

class KeepaliveMessage(QQMessage):
    ''' 心跳消息 '''

    def __init__(self):
        self.msgtype = 3

    def send(self, context):
        url = "http://webqq.qq.com/web2/get_msg_tip?uin=&tp=1&id=0&retype=1&rc=2&lv=3&t="+str(time.time())
        return context.spawn(url, task = context.sendget)

class LogoutMessage(QQMessage):
    '''
    注销消息
    '''
    def __init__(self):
        self.msgtype = 4

    def sendOk(self, result):
        print result.get()

    def send(self, context, clientid, psessionid):
        logouturl = "http://d.web2.qq.com/channel/logout2?ids=&clientid="+clientid+"&psessionid="+psessionid+"&t="+str(time.time())
        return context.spawn(logouturl, task = context.sendget, linkok = self.sendOk)

class MessageFactory(object):
   

    @staticmethod
    def getMessage(webcontext, message):

        msgtype = struct.unpack("i", message[:4])[0]

        if msgtype == 1:
            tolen, bodylen = struct.unpack("ii", message[4:12])
            to, body = struct.unpack("%ss%ss" % (tolen, bodylen), message[12:])
            uin = webcontext.get_uin_by_name(to)
            return QQMessage(uin, body.decode("utf-8"), context = webcontext)

        if msgtype == 2:
            tolen = struct.unpack("i", message[4:8])
            to = struct.unpack("%ss" % tolen, message[8:])
            uin = webcontext.get_uin_by_name(to)
            return ShakeMessage(uin)

        if msgtype == 4:
            return LogoutMessage()

class WebQQ(object):

    def __init__(self):
        self.qq="10897944"
        self.ptwebqq=""
        self.psessionid=""
        self.clientid=str(random.randint(1,99999999))
        self.vfwebqq=""
        self.vcode=""
        self.uin=""
        self.ckjar = cookielib.MozillaCookieJar("/tmp/cookies.txt")
        self.cookiejar = urllib2.HTTPCookieProcessor(self.ckjar)
        self.opener = urllib2.build_opener(self.cookiejar, WebqqHandler)
        self.fakeid = ""
        self.friends = None

        self.mq = queue.Queue(20)
        self.taskpool = pool.Pool(10)
        self.runflag = False
        self.msgindex = random.randint(1,99999999)
        from redis import Redis
        self.redisconn = Redis()
        self.logger = getLogger()

    def build_userinfo(self):
        self.friendinfo = {}
        for friend in self.friends["result"]["marknames"]:
            self.friendinfo[friend["markname"]] = friend["uin"]
            self.friendinfo[friend["uin"]] = friend["markname"]
        
        for friend in self.friends["result"]["info"]:
            if not self.friendinfo.has_key(friend["uin"]):
                self.friendinfo[friend["nick"]] = friend["uin"]
                self.friendinfo[friend["uin"]] = friend["nick"]

    def gethashpwd(self):
        w = "14yhl9t"
        return md5(\
                md5(\
                    (md5(w).digest()+self.uin)\
                    ).hexdigest().upper()+self.vcode\
                  ).hexdigest().upper()

    def login1(self):
        login1url = "http://ptlogin2.qq.com/login?u="+self.qq+"&p="+self.gethashpwd()+"&verifycode="+self.vcode+"&webqq_type=10&remember_uin=1&login2qq=1&aid=1003903&u1=http%3A%2F%2Fwebqq.qq.com%2Floginproxy.html%3Flogin2qq%3D1%26webqq_type%3D10&h=1&ptredirect=0&ptlang=2052&from_ui=1&pttype=1&dumy=&fp=loginerroralert&action=1-20-8656&mibao_css=m_webqq&t=1&g=1"

        self.opener.open(login1url)
        self.ptwebqq = self.ckjar._cookies[".qq.com"]["/"]["ptwebqq"].value
        return self

    def login(self):

        loginurl = "http://check.ptlogin2.qq.com/check?uin=%s&appid=1003903&r=%s"
        response = self.opener.open(loginurl % (self.qq,random.random())).read()
        retcode, vcode, uin = eval(response[12:-1]) 
        if retcode !='0':
            raise WebQQException("Get VCODE Failed!")

        self.vcode = vcode
        self.uin = uin
        return self

    def login2(self):
        login2url = "http://d.web2.qq.com/channel/login2"
        encodeparams = "r=%7B%22status%22%3A%22online%22%2C%22ptwebqq%22%3A%22"+self.ptwebqq+"%22%2C%22passwd_sig%22%3A%22%22%2C%22clientid%22%3A%22"+self.clientid+"%22%2C%22psessionid%22%3Anull%7D&clientid="+self.clientid+"&psessionid=null"
        response = json.loads(self.opener.open(login2url, encodeparams).read())
        if response["retcode"] !=0:
            raise WebQQException("login2 failed! errcode=%s, errmsg=%s"\
                    % (response["retcode"], response["errmsg"]))

        self.vfwebqq = response["result"]["vfwebqq"]
        self.psessionid = response["result"]["psessionid"]
        self.fakeid = response["result"]["uin"]
        self.logger.info("登陆成功！")
        return self


    def get_friends(self):
        getfriendurl = "https://s.web2.qq.com/api/get_user_friends2"
        encodeparams = "r=%7B%22h%22%3A%22hello%22%2C%22vfwebqq%22%3A%22"+self.vfwebqq+"%22%7D"
        getfriendreq = urllib2.Request(getfriendurl, encodeparams)
        getfriendreq.add_header("Referer","http://d.web2.qq.com/proxy.html?v=20110331002&callback=2")
        getfriendreq.add_header("User-Agent","Mozilla/5.0 (X11; Linux i686; rv:16.0) Gecko/20100101 Firefox/16.0")

        self.friends = json.loads(urllib2.urlopen(getfriendreq, timeout=120).read())
        self.build_userinfo()

        if self.friends["retcode"]!=0:
            raise WebQQException("get_friends failed")
        self.logger.info("获取朋友列表...")
        return self

    def write_message(self, qqmsg):
        try:
            self.mq.put_nowait(qqmsg)
        except gevent.queue.Full:
            self.logger.error("%s 发送失败, 队列已满" % str(qqmsg))

    def sendpost(self, url, message,headerdict=None, timeoutsecs=30):
        sendrequest = urllib2.Request(url, message)
        sendrequest.add_header("Referer","http://d.web2.qq.com/proxy.html?v=20110331002&callback=1&id=2")
        sendrequest.add_header("User-Agent","Mozilla/5.0 (X11; Linux i686; rv:16.0) Gecko/20100101 Firefox/16.0")

        if headerdict:
            for k,v in headerdict.iteritems():
                sendrequest.add_header(k,v)

        try:
            return json.loads(urllib2.urlopen(sendrequest, timeout=timeoutsecs).read())
        except urllib2.URLError, urlex:
            raise WebQQException(urlex)

    def sendget(self, url):
        response = self.opener.open(url).read()
        return json.loads(response)

        
    def send_message(self):

         while 1:
            try:
                message = self.redisconn.lpop("messagepool")
                if message:
                    print "got message"
                    qqmesg = MessageFactory.getMessage(self, message)

                    if isinstance(qqmesg, LogoutMessage):
                        print "logout message"

                    qqmesg.send(self, self.clientid, self.psessionid)    

                innermsg = self.mq.get_nowait()
                innermsg.send(self, self.clientid, self.psessionid)

                gevent.sleep(0.1)    

            except gevent.queue.Empty: 
                gevent.sleep(0.1)

            except greenlet.GreenletExit:
                self.logger.info("send_message exitting......")
                break
            except:
                pass

               

    def poll_message(self):
        poll_mess_url = "https://d.web2.qq.com/channel/poll2"
       
        encodeparams = "r=%7B%22clientid%22%3A%22"+self.clientid+"%22%2C%22psessionid%22%3A%22"+self.psessionid+"%22%2C%22key%22%3A0%2C%22ids%22%3A%5B%5D%7D&clientid="+self.clientid+"&psessionid="+self.psessionid

        while 1:
            try:
                if not self.runflag:
                    break

                response = self.sendpost(poll_mess_url, encodeparams, timeoutsecs=60)
                retcode = response["retcode"]

                if retcode == 0:
                    result = response["result"]
                    for message in result:
                        poll_type, value = message["poll_type"], message["value"]
                        # print value

                        if poll_type == "buddies_status_change":
                            fromwho, status = self.get_user_info(value["uin"]), value["status"].encode("utf-8")
                            textoutput(2, "用户 [%s] 在线状态变为 ,%s" % (fromwho, status))

                        if poll_type == "message":
                            fromwho, mess = self.get_user_info(value["from_uin"]), value["content"][1:]
                            messagebody = map(lambda item:":face"+str(item[1])+": " if isinstance(item, list) else item, mess)
                            textoutput(1, "朋友 [%s] 说 %s" % (fromwho, "".join(messagebody).encode("utf-8")))

                        if poll_type == "shake_message":
                            fromwho = self.get_user_info(value["from_uin"])
                            textoutput(3, "朋友 [%s] 给你发送一个窗口抖动 :)" % fromwho)
                            self.write_message(ShakeMessage(value["from_uin"]))

                        if poll_type == "kick_message":
                            print "当前账号已经在别处登陆！"
                            self.stop()
                            break
                        
                elif retcode == 102:
                    print "没收到消息，超时..."

                gevent.sleep(0)

            except WebQQException, webex:
                import traceback
                traceback.print_exc()
                print webex

            except greenlet.GreenletExit:
                self.logger.info("poll_message exitting......")
                break

            except Exception, e:
                import traceback
                traceback.print_exc()

    def keepalive(self):
        
        while 1:
            try:
                KeepaliveMessage().send(self)
                gevent.sleep(60)
            except greenlet.GreenletExit:
                self.logger.info("Keepalive exitting......")
                break

    def get_user_info(self, uin):
        return self.friendinfo.get(uin, str(uin)).encode("utf-8")

    def get_uin_by_name(self, name):
        return self.friendinfo.get(name.decode("utf-8"), None)

    def start(self):
        self.runflag = True

        self.login().login1().login2().get_friends()
        self.taskpool.spawn(self.send_message)
        self.taskpool.spawn(self.poll_message)
        self.taskpool.spawn(self.keepalive)

        self.installsignal()
        self.taskpool.join()
    
    def stop(self):
        LogoutMessage().send(self, self.clientid, self.psessionid)
        self.taskpool.kill()

    def spawn(self, *args, **kwargs):

        g = gevent.spawn(kwargs["task"], *args)
        self.taskpool.add(g)

        if kwargs.get("linkok"):
            g.link(kwargs["linkok"])
        if kwargs.get("linkfailed"):
            g.link_exception(kwargs["linkfailed"])

        return g

    def installsignal(self):
        import signal
        gevent.signal(signal.SIGTERM, self.stop)
        gevent.signal(signal.SIGINT, self.stop)

    def logout(self):
        LogoutMessage().send(self, self.clientid, self.psessionid).get()
        self.stop()

if __name__ == '__main__':

    qq = WebQQ()
    try:
        qq.start()
    except:
        qq.logout()
