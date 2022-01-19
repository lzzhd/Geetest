#!/usr/bin/python
# coding=utf-8
import io
from PIL import Image
import re
import random
import requests
import time
from Geetest_Track import GTrace
from loguru import logger


def get_e() -> str:
    """
    :return: 加密所需的随机字符串
    """
    data = ""
    for i in range(4):
        data += (format((int((1 + random.random()) * 65536) | 0), "x")[1:])
    return data


class Track(object):
    def __init__(self):
        pass

    def __get_standard_img(self, content: bytes) -> object:
        """
        :param content: 二进制图片
        :return: 还原后的图片对象
        """
        position = [39, 38, 48, 49, 41, 40, 46, 47, 35, 34, 50, 51, 33, 32, 28, 29, 27, 26, 36, 37, 31, 30, 44, 45, 43,
                    42, 12,
                    13, 23, 22, 14, 15, 21, 20, 8, 9, 25, 24, 6, 7, 3, 2, 0, 1, 11, 10, 4, 5, 19, 18, 16, 17]
        image = Image.open(io.BytesIO(content))
        standard_img = Image.new("RGBA", (260, 160))
        s, u = 80, 10
        for c in range(52):
            a = position[c] % 26 * 12 + 1
            b = s if position[c] > 25 else 0
            im = image.crop(box=(a, b, a + 10, b + 80))
            standard_img.paste(im, box=(c % 26 * 10, 80 if c > 25 else 0))
        return standard_img

    def __download_image(self, session: object, gap_bg_url: str, full_bg_url: str) -> tuple:
        """
        对滑块所需的图片进行还原,保存
        @param gap_bg_url: 带缺口的背景url
        @param full_bg_url: 不带缺口的背景url
        @return: 还原后的图片对象
        """
        try:
            res_gap_bg = session.get(url=gap_bg_url, timeout=5)
            res_full_bg = session.get(url=full_bg_url, timeout=5)
            # 还原背景图
            standard_res_gap_bg = self.__get_standard_img(res_gap_bg.content)
            standard_res_full_bg = self.__get_standard_img(res_full_bg.content)
            return standard_res_gap_bg, standard_res_full_bg
        except Exception as e:
            raise e

    def __get_distance(self, gap_bg_obj: object, full_bg_obj: object) -> int:
        """
          拿到滑动验证码需要移动的距离
          :param gap_bg_obj:带缺口的图片对象
          :param full_bg_obj:没有缺口的图片对象
          :return:需要移动的距离
        """
        threshold = 50
        for i in range(0, gap_bg_obj.size[0]):  # 260
            for j in range(0, gap_bg_obj.size[1]):  # 160
                pixel1 = gap_bg_obj.getpixel((i, j))
                pixel2 = full_bg_obj.getpixel((i, j))
                res_R = abs(pixel1[0] - pixel2[0])  # 计算RGB差
                res_G = abs(pixel1[1] - pixel2[1])  # 计算RGB差
                res_B = abs(pixel1[2] - pixel2[2])  # 计算RGB差
                if res_R > threshold and res_G > threshold and res_B > threshold:
                    return int(i - 6)

    @classmethod
    def track_run(cls, session, bg_url, full_url):
        bg, full = cls().__download_image(session, bg_url, full_url)
        track = cls().__get_distance(bg, full)
        logger.debug(f'生成缺口距离:{track}')
        return track


class Geetest(Track):
    def __init__(self):
        self.randoms = get_e()
        self.t = int(time.time() * 1000)
        self.s = requests.session()
        self.headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
            'referer': 'https://www.geetest.com/demo/slide-float.html'
        }
        self.s.headers.update(self.headers)

    def get_gt_challenge(self):
        '''
        第一步请求获取gt和challenge值
        :return: gt和challenge
        '''
        url = f'https://www.geetest.com/demo/gt/register-slide?t={self.t}'
        res = self.s.get(url).json()
        item = dict()
        item['challenge'] = res['challenge']
        item['gt'] = res['gt']
        return item

    def get_apiv6(self, gt: str):
        '''
        第二步请求
        :param gt:
        :return:
        '''
        url = f'https://apiv6.geetest.com/gettype.php?gt={gt}&callback=geetest_{self.t}'
        self.s.get(url)

    def __get_w(self, item: dict):
        '''
        获取第一个加密w
        :param item:
        :return:
        '''
        w_api = 'http://127.0.0.1:3000/data'
        data = {
            'key': '1',
            'gt': item['gt'],
            'challenge': item['challenge'],
            'random': self.randoms
        }
        res = requests.post(w_api, data=data).json()['data']
        item['w'] = res

    def get_s(self, item: dict):
        '''
        第三步请求获取s值
        :param item:
        :return:
        '''
        self.__get_w(item)
        data = {
            'gt': item['gt'],
            'challenge': item['challenge'],
            'lang': 'zh-cn',
            'pt': '0',
            'client_type': 'web',
            'w': item['w'],
            'callback': f'geetest_{self.t}'
        }
        url = f'https://apiv6.geetest.com/get.php'
        res = self.s.get(url, params=data).text
        item['s'] = re.findall('"s": "(.*?)"', res)[0]

    def __get_w2(self, item: dict):
        '''
        获取第二次加密w值
        :param item:
        :return:
        '''
        w_api = 'http://127.0.0.1:3000/data'
        data = {
            'key': '2',
            'gt': item['gt'],
            'challenge': item['challenge'],
            'random': self.randoms,
            's': item['s']
        }
        res = requests.post(w_api, data=data).json()['data']
        item['w2'] = res

    def get_fullpage(self, item: dict):
        '''
        第四请求，验证w值，通过无感
        :param item:
        :return:
        '''
        self.__get_w2(item)
        url = 'https://api.geetest.com/ajax.php'
        data = {
            'gt': item['gt'],
            'challenge': item['challenge'],
            'lang': 'zh-cn',
            'pt': '0',
            'client_type': 'web',
            'w': item['w2'],
            'callback': f'geetest_{self.t}'
        }
        res = self.s.get(url, params=data).text
        item.pop('w')
        item.pop('w2')
        logger.debug(f'无感验证:{res}')

    def get_slide_data(self, item: dict):
        '''
        第五步请求，获取滑块参数
        :param item:
        :return:
        '''
        url = 'https://api.geetest.com/get.php'
        data = {
            'is_next': 'true',
            'type': 'slide3',
            'gt': item['gt'],
            'challenge': item['challenge'],
            'lang': 'zh-cn',
            'https': 'true',
            'protocol': 'https://',
            'offline': 'false',
            'product': 'embed',
            'api_server': 'api.geetest.com',
            'isPC': 'true',
            'autoReset': 'true',
            'width': '100%',
            'callback': f'geetest_{self.t}'
        }
        res = self.s.get(url, params=data).text
        item['gt'] = re.findall('"gt": "(.*?)"', res)[0]
        item['challenge'] = re.findall('"challenge": "(.*?)"', res)[0]
        item['s'] = re.findall('"s": "(.*?)"', res)[0]
        item['bg'] = 'https://static.geetest.com/' + re.findall('"bg": "(.*?)"', res)[0]
        item['fullbg'] = 'https://static.geetest.com/' + re.findall('"fullbg": "(.*?)"', res)[0]

    def math_slide(self, item: dict):
        '''
        计算滑块距离
        生成轨迹
        :param item:
        :return:
        '''
        item['distance'] = super().track_run(self.s, item['bg'], item['fullbg'])
        item['trajectory'] = GTrace().get_mouse_pos_path(item['distance'])

    def __get_w3(self, item: dict):
        '''
        获取第三次加密w值
        :param item:
        :return:
        '''
        w_api = 'http://127.0.0.1:3000/data'
        data = {
            'key': '3',
            'gt': item['gt'],
            'challenge': item['challenge'],
            'random': self.randoms,
            's': item['s'],
            'e': str(item['trajectory']),
            't1': item['distance'],
            't2': item['trajectory'][-1][2]
        }
        res = requests.post(w_api, data=data).json()['data']
        item['w'] = res

    def get_slide(self, item: dict):
        self.__get_w3(item)
        url = 'https://api.geetest.com/ajax.php'
        data = {
            'gt': item['gt'],
            'challenge': item['challenge'],
            'lang': '0',
            '$_BBF': '0',
            'client_type': 'web',
            'w': item['w'],
            'callback': f'geetest_{self.t}'
        }
        res = self.s.get(url, params=data)
        logger.debug(f'滑块验证:{res.text}')

    def run(self):
        item = self.get_gt_challenge()  # 获取无感参数
        self.get_apiv6(item['gt'])
        self.get_s(item)  # 获取第一次s值
        self.get_fullpage(item)  # 验证无感
        self.get_slide_data(item)  # 获取滑块参数
        self.math_slide(item)  # 计算距离生成轨迹
        self.get_slide(item)  # 验证滑块

    def main(self):
        self.run()


if __name__ == '__main__':
    Geetest().main()
