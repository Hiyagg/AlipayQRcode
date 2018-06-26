# coding:utf8
import uiautomator2 as u2
import time
import requests
import re
import hashlib
import threading
import logging
import datetime
import pymysql


"""
监控支付宝到账通知，获取订单信息，记录并发送回调给服务器
"""
logging.basicConfig(level=logging.INFO,
                format='%(asctime)s %(funcName)s %(levelname)s %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S',
                filename='log.log',
                filemode='a')

info = logging.info
warning = logging.warning


class Phone(object):

    mysql = ''  # Mysql连接
    cur = ''  # 游标

    def __init__(self, ip, acountinfo):
        self.orderlast = [{'billName': '', 'billAmount': '', 'timeInfo': ''}]
        self.orderlast[0]['billName'], self.orderlast[0]['billAmount'], self.orderlast[0]['timeInfo'] = self.sql_serch(acountinfo)
        self.ordernew = []
        self.pages = 0
        self.ct = u2.connect(ip)

    # 获取界面信息，匹配订单数据，筛选，返回新订单
    def findbill(self):
        time.sleep(0.2)
        info('Try get data')
        # 找到当前屏幕内所有的显示完整订单
        billlist = self.ct.dump_hierarchy()
        pattern = re.compile('(\\d{18,20})[\\s\\S]*?([+]\\d{1,5}\\.\\d\\d)[\\s\\S]*?(\\d\\d:\\d\\d)')  #匹配订单备注，订单金额，交易时间
        bills = pattern.findall(billlist)
        if not bills:
            warning('No new order , try open app again')  # 没有读取到订单 重新打开支付宝进入账单界面
            self.openapp(0)
            return 1

        for bill in bills:
            billname, billamount, timeinfo = bill[0], bill[1], bill[2].replace(':', '')+'00'
            billdata = {'billAmount': billamount[1:], 'billName': billname,
                        'timeInfo': '%s' % timeinfo}  # 订单格式
            if billdata in self.ordernew:  # 如果已在本次订单列表中，则跳过该笔订单
                continue
            elif billdata in self.orderlast:  # 如果已在上次的订单列表中，则结束读取
                return 0  # 返回0，告知完毕
            else:
                self.ordernew.append(billdata)  # 否则添加到新订单列表
        info('all bills are new, continue find')
        self.pages += 1
        self.ct.swipe(0.5, 0.85, 0.5, 0.1, 0.5)
        return 1  # 上滑查看更多订单，返回1，继续获取


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
        # input('读取获取完成')
        return self.ordernew

    def openapp(self, restart):
        info('Open alipay app')
        self.ct.app_stop('com.eg.android.AlipayGphone')
        self.ct.app_start('com.eg.android.AlipayGphone')
        self.ct(text='我的').click_exists(5)
        self.ct(text='账单').click_exists(5)
        if restart == 1:
            return 1


    def run(self):
        info('Start Watching')
        while 1:
            restart = 0
            time.sleep(1)
            if self.ct.info['currentPackageName'] != 'com.eg.android.AlipayGphone':
                restart = self.openapp(1)
            if self.ct(text='支付宝通知').exists or restart == 1:
                info('Alipay information，ready to get bills')
                ctime = datetime.datetime.now().strftime('%Y%m%d%H%M%S')  # 当前时间
                self.ct.swipe(0.5, 0.3, 0.5, 0.6, 0.03)  # 下拉刷新账单
                self.ordernew = []  # 新订单表清零

                # 获取订单信息
                st_time = time.time()
                order = self.get()
                use_time = time.time()-st_time
                info('Delay time%s' % use_time)
                # print(order)
                if not order:
                    warning('No new order!!!')
                    continue
                # 发送订单线程
                info('Create new thread to send data')
                threading.Thread(target=self.send_url, args=(order, ctime)).start()
                # 返回订单顶部
                for i in range(self.pages):
                    self.ct.swipe(0.5, 0.1, 0.5, 0.85, 0.3)
                self.pages = 0

    @classmethod
    def send_url(cls, order, ctime):  # 发送回调
        info('Start send order data')
        key = '123456'
        for oneorder in order:
            msg = 'billAmount=%s&billName=%s&timeInfo=%s' % \
                  (oneorder['billAmount'], oneorder['billName'], ctime[:8] + oneorder['timeInfo'])
            info('Original str: %s' % msg)
            msg_key = msg + '&key=' + key
            md5 = hashlib.md5()
            md5.update(msg_key.encode(encoding='utf-8'))
            sign = md5.hexdigest()
            msg_send = msg + '&sign=' + sign
            input(msg_send)
            info('Signed str: %s' % msg_send)
            order_id = ctime + '%02d' % order.index(oneorder)
            for sendtimes in range(2):
                try:
                    info('Sending')
                    response = requests.post('http://112.74.40.81:11150/cgi-bin/v2.0/api_ali_pay_pqrcode_notify.cgi',
                                             data=msg_send)
                    recode = response.text
                    print('Reply: %s' % recode)
                    info('Reply: %s' % recode+' write to db')
                    if recode == 'success':
                        cls.sql_insert(ctime, oneorder, order_id, status='1')
                    else:
                        cls.sql_insert(ctime, oneorder, order_id, status='2')
                    break
                except Exception as e:
                    if sendtimes == 0:
                        warning('Failed, Error：%s,try again' % e)
                    else:
                        warning('Failed again, Error：%s,write to db' % e)
                        cls.sql_insert(ctime, oneorder, order_id, status='0')
                    continue
            info('Send complete')

    @classmethod
    def sql_insert(cls, ctime, oneorder, order_id, status):
        info('connect mysql and insert into table')
        cls.sql_conn()
        acountinfo, billname, billamount, timeinfo = oneorder['billName'][:9], oneorder['billName'], \
                                             oneorder['billAmount'], oneorder['timeInfo']
        sql = "INSERT INTO `orders`.`new_table` (`acountinfo`, `billname`, `billamount`, `timeinfo`, " \
              "`ctime`, `status`,`order_id`) VALUES (%s,%s,%s,%s,%s,%s,%s);"\
              % (acountinfo, billname, billamount, timeinfo, ctime, status, order_id)
        #input(sql)
        cls.cur.execute(sql)
        cls.mysql.commit()
        cls.sql_close()
        info('over , close')

    @classmethod
    def sql_serch(cls, acountinfo):
        info('connect mysql and search the last order')
        cls.sql_conn()
        sql = "SELECT billname,billamount,timeinfo FROM `orders`.`new_table` WHERE acountinfo=%s ORDER BY ctime DESC limit 0,5" % acountinfo
        #input(sql)
        cls.cur.execute(sql)
        order_data = cls.cur.fetchmany(1)[0]
        #input(order_data)
        cls.sql_close()
        info('over , close and return')
        #return order_data
        return ('123456002000001001','0.10','200400') #测试

    @classmethod
    def sql_conn(cls):
        cls.mysql = pymysql.connect(host='54.176.208.157', port=3306, user='admin', passwd='131415', db='orders')
        cls.cur = cls.mysql.cursor()

    @classmethod
    def sql_close(cls):
        cls.cur.close()
        cls.mysql.close()


if __name__ == '__main__':
    address = '192.168.43.87'
    info('Phone ip: %s' % address)
    phone01 = Phone(address, '123456002')
    phone01.run()

