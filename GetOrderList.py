# coding:utf8
import uiautomator2 as u2
import time
import requests
import re
import hashlib
import threading
import logging
import datetime

logging.basicConfig(level=logging.INFO,
                format='%(asctime)s %(funcName)s %(levelname)s %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S',
                filename='log.log',
                filemode='a')

info = logging.info
warning = logging.warning

class Phone(object):
    def __init__(self, ip):
        self.orderlast = [{'billName': '800012345612000212', 'billAmount': '0.20', 'timeInfo': '20180614212100'}]
        self.ordernew = []
        self.pages = 0
        self.ct = u2.connect(ip)


    def findbill(self):#获取界面信息，匹配订单数据，筛选，返回新订单
        time.sleep(0.2)
        info('Try get data')

        billlist = self.ct.dump_hierarchy()
        pattern = re.compile('.*(\\d{18,20})[\\s\\S]*?([+]\\d{1,5}\\.\\d\\d)[\\s\\S]*?(\\d\\d:\\d\\d).*')  #匹配订单备注，订单金额，交易时间
        bills = pattern.findall(billlist) #找到当前屏幕内所有的显示完整订单
        if not bills:
            warning('No new order , try open app again')#没有读取到订单 重新打开支付宝进入账单界面
            self.openapp(0)
            return 1

        for bill in bills:
            billname, billamount, timeinfo = bill
            billdata = {'billAmount': billamount[1:], 'billName': billname,
                        'timeInfo': '%s' % datetime.date.today().strftime('%Y%m%d')+timeinfo.replace(':', '')+'00'} #订单格式
            if billdata in self.ordernew: #如果已在本次订单列表中，则跳过该笔订单
                continue
            elif billdata in self.orderlast: #如果已在上次的订单列表中，则结束读取
                return 0  #返回0，告知完毕
            else:
                self.ordernew.append(billdata) #否则添加到新订单列表
        info('all bills are new, continue find')
        self.pages += 1
        self.ct.swipe(0.5, 0.85, 0.5, 0.1, 0.5)
        return 1 #上滑查看更多订单，返回1，继续获取


    def get(self):
        info('start get new order')
        flag = self.findbill()
        while flag:
            flag = self.findbill()
        info('Get complete')
        if self.ordernew:
            with open('record.txt', 'w') as f:  # 储存在本地
                f.write(str(self.ordernew))
            self.orderlast = self.ordernew  # 记录本次的获取订单列表
        #input('读取获取完成')
        return self.ordernew

    def openapp(self, restart):
        info('Open alipay app')
        self.ct.app_stop('com.eg.android.AlipayGphone')
        self.ct.app_start('com.eg.android.AlipayGphone')
        self.ct(text='我的').click_exists(5)
        self.ct(text='账单').click_exists(3)
        if restart == 1:
            return 1


    def run(self):
        info('Start Watching')
        while 1:
            restart = 0
            time.sleep(0.5)
            if self.ct.info['currentPackageName'] != 'com.eg.android.AlipayGphone' or self.ct(text='通知').exists:
                restart = self.openapp(1)
            if self.ct(text='支付宝通知').exists or restart == 1:
                info('Alipay information，ready to get bills')

                self.ct.swipe(0.5, 0.3, 0.5, 0.6, 0.03)  # 下拉刷新账单
                self.ordernew = []  # 新订单表清零

                #获取订单信息
                st_time = time.time()
                order = self.get()
                use_time = time.time()-st_time
                info('Delay time%s' % use_time)
                #print(order)
                if not order:
                    warning('No new order!!!')
                    continue
                # 发送订单线程
                info('Create new thread to send data')
                threading.Thread(target=sendurl, args=(order,)).start()
                # 返回订单顶部
                for i in range(self.pages):
                    self.ct.swipe(0.5, 0.1, 0.5, 0.85, 0.3)
                self.pages = 0

def sendurl(order):#发送回调
    info('Start send order data')
    key = '123456'
    msg = ''
    for i in order:
        for x, y in i.items():
            msg += x + '=' + y + '&'
        info('Original str: %s' % msg[:-1])
        msg_key = msg + 'key='+key
        md5 = hashlib.md5()
        md5.update(msg_key.encode(encoding='utf-8'))
        sign = md5.hexdigest()
        msg_send = msg+'sign='+sign
        input(msg_send)
        info('Signed str: %s' % msg_send)
        for sendtimes in range(2):
            try:
                info('Sending')
                response = requests.post('http://112.74.40.81:11150/cgi-bin/v2.0/api_ali_pay_pqrcode_notify.cgi', data=msg_send)
                recode = response.text
                #if recode =! ''
                info('Reply: %s' % recode)
                print('Reply: %s' % recode)
                break
            except Exception as e:
                warning('Failed, Error：%s,try again' % e)
                continue
    info('Send complete')


if __name__ == '__main__':
    ip = '192.168.137.47'
    info('Phone ip: %s' % ip)
    phone01 = Phone(ip)
    phone01.run()

