# -*- coding:utf-8 -*-

import urllib2, cookielib
import json
from urllib2 import BaseHandler
import random
from hashlib import md5
import gevent
from gevent import monkey, queue
import socket
monkey.patch_socket()
monkey.patch_select()
socket.setdefaulttimeout(30)

GET_VCODE_URL = "http://check.ptlogin2.qq.com/check?uin=%s&appid=1003903&r=%s"

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

class QQMessage(object):

    def __init__(self, to, messagetext,msgtype=9):
        self.msgtype = msgtype
        self.to = to 
        self.messagetext
    
    def __str__(self):
        
        r={"to":self.to,"face":567,"content":"[\""+self.messagetext+"\\n\",[\"font\",{\"name\":\"宋体\",\"size\":\"10\",\"style\":[0,0,0],\"color\":\"000000\"}]]","msg_id":MessageIndex.get(),"clientid":"[clientid]","psessionid":"[psessionid]"}
        return self.messagetext

class ShakeMessage(QQMessage):
    '''
    发送窗口抖动消息
    '''
    pass

class TextMessage(QQMessage):
    '''
    文本消息，不带表情 
    '''
    def __init__(self):pass

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
        self.msgindex = random.randint(1,99999999)

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
        response = self.opener.open(GET_VCODE_URL % (self.qq,random.random())).read()
        retcode, vcode, uin = eval(response[12:-1]) 
        if retcode !='0':
            raise WebQQException()

        self.vcode = vcode
        self.uin = uin
        return self

    def login2(self):
        login2url = "http://d.web2.qq.com/channel/login2"
        encodeparams = "r=%7B%22status%22%3A%22online%22%2C%22ptwebqq%22%3A%22"+self.ptwebqq+"%22%2C%22passwd_sig%22%3A%22%22%2C%22clientid%22%3A%22"+self.clientid+"%22%2C%22psessionid%22%3Anull%7D&clientid="+self.clientid+"&psessionid=null"
        login2request = urllib2.Request(login2url, encodeparams)
        login2request.add_header("Referer","http://d.web2.qq.com/proxy.html?v=20110331002&callback=1&id=2")
        response = json.loads(self.opener.open(login2url, encodeparams).read())
        self.vfwebqq = response["result"]["vfwebqq"]
        self.psessionid = response["result"]["psessionid"]
        self.fakeid = response["result"]["uin"]
        print "登陆成功..."
        return self

    def start(self):
        self.login().login1().login2().get_friends()
        gevent.joinall([gevent.spawn(self.send_message), gevent.spawn(self.poll_message)])

    def get_friends(self):
        print "获取朋友列表..."
        getfriendurl = "http://s.web2.qq.com/api/get_user_friends2"
        encodeparams = "r=%7B%22h%22%3A%22hello%22%2C%22vfwebqq%22%3A%22"+self.vfwebqq+"%22%7D"
        getfriendreq = urllib2.Request(getfriendurl, encodeparams)
        getfriendreq.add_header("Referer","http://d.web2.qq.com/proxy.html?v=20110331002&callback=2")
        getfriendreq.add_header("User-Agent","Mozilla/5.0 (X11; Linux i686; rv:16.0) Gecko/20100101 Firefox/16.0")

        self.friends = json.loads(urllib2.urlopen(getfriendreq).read())
        self.build_userinfo()
        with open("/tmp/firends.json", "w") as friends:
            friends.write(json.dumps(self.friendinfo))

        if self.friends["retcode"]!=0:
            raise WebQQException("get_friends failed")
        return self
    def get_userinfo(self, uin):
        pass

    def write_message(self, qqmsg):
        try:
            self.mq.put_nowait(qqmsg)
        except gevent.queue.Full:
            print "%s 发送失败, 队列已满" % str(qqmsg)

    def get_message(self, msgtype=9, to=0, messbody=""):
        pass

    def send_message(self):
        while 1:
            try:
                qqmesg = self.mq.get()
                print "准备发送消息" % str(qqmesg)
                # gevent.sleep(1)
            except gevent.queue.Empty:
                pass

    def poll_message(self):
        poll_mess_url = "http://d.web2.qq.com/channel/poll2"
       
        encodeparams = "r=%7B%22clientid%22%3A%22"+self.clientid+"%22%2C%22psessionid%22%3A%22"+self.psessionid+"%22%2C%22key%22%3A0%2C%22ids%22%3A%5B%5D%7D&clientid="+self.clientid+"&psessionid="+self.psessionid

        while 1:
            try:

                pollreq = urllib2.Request(poll_mess_url, encodeparams)
                pollreq.add_header("Referer","http://d.web2.qq.com/proxy.html?v=20110331002&callback=1&id=3")
                pollreq.add_header("User-Agent","Mozilla/5.0 (X11; Linux i686; rv:16.0) Gecko/20100101 Firefox/16.0")
                response = json.loads(urllib2.urlopen(pollreq).read())
                retcode = response["retcode"]
                if retcode == 0:
                    result = response["result"]
                    for message in result:
                        poll_type, value = message["poll_type"], message["value"]
                        print value
                        if poll_type == "buddies_status_change":
                            print "用户状态变更消息"
                        if poll_type == "message":
                            fromwho, mess = self.friendinfo[value["from_uin"]].encode("utf-8"), value["content"][1:]
                            messagebody = map(lambda item:":face"+str(item[1])+": " if isinstance(item, list) else item, mess)
                            print "朋友 %s 说 %s" % (fromwho, "".join(messagebody).encode("utf-8"))
                        if poll_type == "shake_message":
                            fromwho = self.friendinfo[value["reply_ip"]]
                            print "朋友 %s 给你发送一个窗口抖动 :)" % fromwho
                        
                elif retcode == 102:
                    print "没收到消息，超时..."

                gevent.sleep(0)

            except Exception, e:
                import traceback
                traceback.print_exc()

if __name__ == '__main__':
    qq = WebQQ()
    qq.start()
