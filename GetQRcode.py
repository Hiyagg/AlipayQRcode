#coding:utf8
import uiautomator2 as u2
import time
from config import phonelist
import threading
import xlwt

d = [u2.connect(i['ip']) for i in phonelist]
qrcode = []


def getqr(d, user, account, qrmoney, qrnum):
    d.app_start('com.eg.android.AlipayGphone')
    #d(text='收钱').click_exists(1)
    d(text='设置金额').click()
    #d.set_fastinput_ime(True) # 切换成FastInputIME输入法
    d.send_keys(str(float(qrmoney)/100)) # adb广播输入

    d(text='添加收款理由').click()

    d.send_keys("%s%s%s%s" % (user, account, qrmoney, qrnum)) # adb广播输入

    d(text='确定').click()
    d(text='保存图片').click()
    #time.sleep(1)
    d(text='清除金额').click()

    d.app_start('mark.qrcode')
    d(text='从图库扫描…').click()
    if account == '001':
        d.tap(0.26, 0.32)
    elif account == '002':
        d.tap(0.282, 0.814)
        d.tap(0.125, 0.3)
    elif account == '003':
        d.tap(0.2, 0.3)
    #time.sleep(0.2)
    url = d(resourceId="mark.qrcode:id/p").get_text()
    d.press('back')
    return "%s%s%s%s" % (user, account, qrmoney, qrnum), url


def creatbill(i, user, account):
    qr = []
    print(threading.currentThread())
    t0 = time.time()
    for qrmoney in [x for x in range(10, 51) if x % 10 == 0]:
        qrmoney = "%07d" % qrmoney
        for qrnum in range(1, 3):
            qrnum = "%02d" % qrnum
            #input("%s%s%s%s" % (user, account, qrmoney, qrnum))
            qr.append(getqr(d[i], user, account, qrmoney, qrnum))
    t = time.time()-t0
    print(t, qr)


for i in range(3): #三台手机
    user, account = phonelist[i]['user'], phonelist[i]['account']
    threading.Thread(target=creatbill, args=(i, user, account)).start()
print(threading.enumerate())