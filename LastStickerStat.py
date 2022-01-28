from bs4 import BeautifulSoup
import datetime
import json
import os
import pandas as pd
import re
import requests
import sys
from tqdm import tqdm
from tqdm.contrib.telegram import tqdm as tq


class LastStickerStat(object):

    def __set_consts(self):
        # Необходимо для корректной работы парсинга запросов через телеграм бот и обновления/загрузки данных
        with open("config.json", "r") as f:
            config = json.load(f)
        self.MAIN_URL = config["MAIN_URL"]
        self.FIRST_AUCTION = config["FIRST_AUCTION"]
        self.FIRST_NEW_AUCTION = config["FIRST_NEW_AUCTION"]
        self.COL_NAMES = config["COL_NAMES"]
        MONTH_NAMES = config["MONTH_NAMES"]
        self.MONTH_TO_NUM = dict((m, str(n)) for (n, m) in enumerate(MONTH_NAMES, start=1))
        self.DECODE_SBJ = config["DECODE_SBJ"]
        self.DECODE_THEME = config["DECODE_THEME"]
        self.DECODE_LOT_TYPE = config["DECODE_LOT_TYPE"]
        self.DECODE_SORT_BY = config["DECODE_SORT_BY"]
        self.DECODE_STATUS = config["DECODE_STATUS"]

    # Либо создаем базу с чистого листа, либо считываем уже существующую
    def __init__(self, file_name, token=""):
        self.__set_consts()
        self.dir_path = "{}".format(file_name)
        self.csv_path = "{}/{}.csv".format(self.dir_path, file_name)
        self.upper_csv_path = "{}/upper_{}.csv".format(self.dir_path, file_name)
        self.json_path = "{}/{}.json".format(self.dir_path, file_name)
        self.csv_batch = 500  # Раз во сколько страниц обновляем содержимое csv
        self.upd_allowed = True  # False, если update() уже вызвали
        self.token = token
        if not os.path.isdir(self.dir_path):
            os.mkdir(self.dir_path)
            # Запуск парсинга с самого начала
            self.__parse_all()
        else:
            # Считывание существующей базы и информации о ней
            self.df = pd.read_csv(self.csv_path, sep=";", low_memory=False)
            self.df_upper = pd.read_csv(self.upper_csv_path, sep=";", low_memory=False)
            with open(self.json_path, "r") as f:
                self.info = json.load(f)

    # Последний созданный лот на сайте на момент вызова этой функции. Как правило это первая ссылка
    # ниже надписи "Все предложения" на странице https://www.laststicker.ru/auction/
    @staticmethod
    def last_lot_url_id_now():
        response = requests.get("https://www.laststicker.ru/auction/")
        soup = BeautifulSoup(response.content, "html.parser")
        return int(soup.find_all("h2")[-2].next_sibling.a["href"][13:-1])

    # Создаем файл csv с пустой базой
    def __write_empty_csv(self):
        pd.DataFrame(columns=self.COL_NAMES).to_csv(self.csv_path, sep=";", header=self.COL_NAMES, index=False)
        pd.DataFrame(columns=["title", "collection"]).to_csv(self.upper_csv_path, sep=";",
                                                             header=["title", "collection"], index=False)

    # Парсим страницы с самого первого лота, доступного на сайте, и до последнего
    def __parse_all(self):
        self.info = {"unparsed_pages": [], "lots_amount": 0}
        self.df = pd.DataFrame(columns=self.COL_NAMES)
        self.df_upper = pd.DataFrame(columns=["title", "collection"])
        self.__write_empty_csv()

        # Обработка староформатных аукционов
        self.__parse_old_to_csv()

        self.info["last_lot_url_id"] = self.last_lot_url_id_now()

        now = datetime.datetime.now()
        self.info["last_lot_parse_date"] = "{}:{} {}.{}.{}".format(now.hour, now.minute, now.day, now.month, now.year)

        # Обработка новоформатных аукционов
        self.__parse_to_csv(self.FIRST_NEW_AUCTION, self.info["last_lot_url_id"], False)

    # Парсинг староформатных лотов
    def __parse_old_to_csv(self):

        passed_pages = 0
        df = pd.DataFrame(columns=self.COL_NAMES)
        df_upper = pd.DataFrame(columns=["title", "collection"])

        for i in tqdm(range(self.FIRST_AUCTION, self.FIRST_NEW_AUCTION)):
            try:
                page_num = i
                url = self.MAIN_URL + "/auction/post{}/".format(page_num)
                response = requests.get(url)

                if response.status_code == 200:

                    # Пропускаем все форумные и иже с ними страницы. Нас интересуют только предложения
                    soup = BeautifulSoup(response.content, "html.parser")
                    if soup.find("div", id="nav").contents[2].text != "Аукцион":
                        raise

                    # Если есть description, чаще всего там написано, карточный или наклеечный это лот
                    tag_description = soup.find("meta", {"name": re.compile("description")})
                    header = "" if tag_description == None else tag_description["content"]

                    # Вытаскиваем заголовок и категорию лота (Хоккейные карточки, Мультфильмы и кино,
                    # Другие виды спорта итд)
                    title = soup.h1.text
                    theme = soup.find("div", id="nav").contents[-1].text

                    # Если попалась категория Другие виды спорта или Мультфильмы и кино, то просто так не поймешь,
                    # карточный или наклеечный это лот. Надо подглядывать в description
                    if theme in ["Другие виды спорта", "Мультфильмы и кино"] and header != "":
                        is_sticker = "наклеек" in header
                        is_card = "карточек" in header
                        is_undefined = not (is_sticker ^ is_card)
                    # Если и description пустой/его нет, то методами парсинга не узнать, наклеечный или карточный
                    # это лот. Определяем предмет лота как Неопределено
                    elif theme in ["Другие виды спорта", "Мультфильмы и кино"]:
                        is_undefined = True
                    # Если категория (theme) лота не Другие виды спорта и не Мультфильмы и кино, тогда легко определим
                    # "предмет" лота (карточки/наклейки/другое)
                    else:
                        is_undefined = False
                        cards = ["Хоккейные карточки", "Футбольные карточки", "Прочие карточки", "ККИ"]
                        stickers = ["Футбольные наклейки", "Хоккейные наклейки", "Прочие наклейки"]
                        is_sticker = theme in stickers
                        is_card = theme in cards
                    is_other = not is_undefined and not (is_sticker or is_card)
                    subject = "Неопределено" if is_undefined else "Карточки" * is_card + \
                                                                  "Наклейки" * is_sticker + "Другое" * is_other
                    # Вытаскиваем url и ник продавца
                    tag_seller = soup.find("div", "head_bg-l clearer").find_all("a", class_="")[1]
                    seller_url = self.MAIN_URL + tag_seller["href"]
                    seller_nickname = tag_seller.text

                    # Вытаскиваем локацию продавца
                    seller_location_city = soup.find("div", class_="forum_left").contents[-1]
                    seller_location_country, seller_location_district = None, None

                    # Вытаскиваем информацию о коллеции лота, если эта инф-я есть
                    tag_album = soup.find_all("div", class_="album_item")
                    if tag_album != [] and tag_album[-1].h3 != None and tag_album[-1].h3.a != None:
                        collection = tag_album[-1].h3.a.text
                        url_collection = self.MAIN_URL + tag_album[-1].h3.a["href"]
                        if "/cards/" not in url_collection:
                            collection, url_collection = None, None
                    else:
                        collection, url_collection = None, None

                    # Вытаскиваем инф-ю о дате создания/закрытия лота
                    date_start_txt = soup.find_all("div", class_="forum_left")[0].span.text
                    date_start = date_start_txt.split("\xa0")
                    date_start[1] = self.MONTH_TO_NUM[date_start[1]]
                    if len(date_start) == 3:
                        date_start.insert(2, str(datetime.datetime.now().year))
                    date_start_day = date_start[0]
                    date_start_month = date_start[1]
                    date_start_year = date_start[2]
                    date_start_time = date_start[3]

                    # Сложно выпарсить дату закрытия староформатного лота, поэтому не будем даже пытаться
                    date_end_day, date_end_month, date_end_year, date_end_time = None, None, None, None

                    # Всю найденную информацию записываем в атрибут объекта класса df и df_upper
                    dct = {"title": title, "url": url, "subject": subject, "theme": theme, "lot_type": "Староформатный",
                           "status": "Закрыт", "is_bet_made": None, "collection": collection,
                           "url_collection": url_collection, "date_start_day": date_start_day,
                           "date_start_month": date_start_month, "date_start_year": date_start_year,
                           "date_start_time": date_start_time, "seller_nickname": seller_nickname,
                           "seller_url": seller_url, "seller_location_city": seller_location_city,
                           "seller_location_district": seller_location_district,
                           "seller_location_country": seller_location_country, "initial_price": None,
                           "last_price": None, "last_price_author": None, "url_last_buyer": None,
                           "date_end_day": date_end_day, "date_end_month": date_end_month,
                           "date_end_year": date_end_year, "date_end_time": date_end_time}
                    df = df.append(dct, ignore_index=True)
                    collection_upper = None if collection == None else collection.upper()
                    df_upper = df_upper.append({"title": title.upper(), "collection": collection_upper},
                                               ignore_index=True)

                    self.df = self.df.append(dct, ignore_index=True)
                    self.df_upper = self.df_upper.append({"title": title.upper(), "collection": collection_upper},
                                                         ignore_index=True)

                    passed_pages += 1

                    # Каждые csv_batch ссылок подгружаем информацию о лотах в csv файл
                    if passed_pages % self.csv_batch == 0:
                        df.to_csv(self.csv_path, sep=";", mode="a", header=False, index=False)
                        df = pd.DataFrame(columns=self.COL_NAMES)
                        df_upper.to_csv(self.upper_csv_path, sep=";", mode="a", header=False, index=False)
                        df_upper = pd.DataFrame(columns=["title", "collection"])

            except Exception:
                self.info["unparsed_pages"].append(url)

        self.info["lots_amount"] += passed_pages

        # Дозаписываем csv файл (у нас мог остаться не записанный кусок)
        df.to_csv(self.csv_path, sep=";", mode="a", header=False, index=False)
        df_upper.to_csv(self.upper_csv_path, sep=";", mode="a", header=False, index=False)

    # Парсинг новоформатных лотов
    def __parse_to_csv(self, first_page, last_page, json_written, chat_id=None):

        passed_pages = 0
        df = pd.DataFrame(columns=self.COL_NAMES)
        df_upper = pd.DataFrame(columns=["title", "collection"])

        rng = tqdm(range(first_page, last_page + 1)) if chat_id == None else tq(range(first_page, last_page + 1),
                                                                                token=self.token, chat_id=chat_id)

        for i in rng:
            try:
                page_num = i
                url = self.MAIN_URL + "/auction/post{}/".format(page_num)
                response = requests.get(url)

                if response.status_code == 200:

                    soup = BeautifulSoup(response.content, "html.parser")
                    if soup.find("div", id="nav").contents[2].text != "Аукцион":
                        raise

                    tag_description = soup.find("meta", {"name": re.compile("description")})
                    header = "" if tag_description == None else tag_description["content"]

                    title = soup.h1.text
                    theme = soup.find("div", id="nav").contents[-1].text

                    if theme in ["Другие виды спорта", "Мультфильмы и кино"] and header != "":
                        is_sticker = "наклеек" in header
                        is_card = "карточек" in header
                        is_undefined = not (is_sticker ^ is_card)
                    elif theme in ["Другие виды спорта", "Мультфильмы и кино"]:
                        is_undefined = True
                    else:
                        is_undefined = False
                        cards = ["Хоккейные карточки", "Футбольные карточки", "Прочие карточки", "ККИ"]
                        stickers = ["Футбольные наклейки", "Хоккейные наклейки", "Прочие наклейки"]
                        is_sticker = theme in stickers
                        is_card = theme in cards
                    is_other = not is_undefined and not (is_sticker or is_card)
                    subject = "Неопределено" if is_undefined else "Карточки" * is_card + \
                                                                  "Наклейки" * is_sticker + "Другое" * is_other
                    # Вытаскиваем дату закрытия лота
                    tag_closed = soup.find("div", id=re.compile("auction_bid_countdown"))
                    is_closed = "Дата и время окончания" in tag_closed.text

                    # Определяем, перед нами аукцион или объявление
                    tag_auction = soup.find("div", {"style": re.compile("float: left; width: 50%")})
                    # Ставок еще не было, если в этом теге есть "Начальная ставка"
                    no_bets = "Начальная ставка" in tag_auction.text
                    # Аукцион завершен и ставка была сделана, если в теге есть "Победная ставка"
                    smbd_won = "Победная ставка" in tag_auction.text
                    # Аукцион открыт и ставка была сделана, если в теге есть "Текущая ставка"
                    is_bet_made = "Текущая ставка" in tag_auction.text

                    is_auction = no_bets or smbd_won or is_bet_made
                    is_bet_made = is_auction and not no_bets  # исправлена ошибка (2)
                    is_offer = not is_auction
                    lot_type = "Аукцион" * is_auction + "Объявление" * is_offer

                    # Если аукцион, то есть информация о ставках. Достаем ее
                    if is_auction:
                        if no_bets:
                            initial_price = tag_auction.contents[1].b.text
                            last_price, last_price_author, url_last_buyer = None, None, None
                        else:
                            initial_price = tag_auction.contents[1].find_all("div")[-1].b.text  # исправлена ошибка
                            tag_last_bet = \
                                tag_auction.contents[1].find_all("div", {"style": re.compile("margin-bottom")})[
                                    -1].next_sibling
                            # Достаем последнего сделавшего ставку
                            if "Контрольное время" in tag_last_bet.text:
                                tag_last_bet = tag_last_bet.next_sibling
                            last_price = tag_last_bet.b.text
                            last_price_author = tag_last_bet.a.text
                            url_last_buyer = self.MAIN_URL + tag_last_bet.a["href"]
                    else:
                        initial_price, last_price, last_price_author, url_last_buyer = None, None, None, None

                    lot_status = is_closed * "Закрыт" + (not is_closed) * "Открыт"

                    tag_seller = soup.find("div", "head_bg-l clearer").find_all("a", class_="")[1]
                    seller_url = self.MAIN_URL + tag_seller["href"]
                    seller_nickname = tag_seller.text

                    seller_location = soup.find("div", {"style": re.compile("margin-top: 30px")}).div.div.contents[
                        -1].split(",")
                    if len(seller_location) == 3:
                        seller_location_country = seller_location[0]
                        seller_location_district = seller_location[1][1:]
                        seller_location_city = seller_location[2][1:]
                    elif len(seller_location) == 2:
                        seller_location_country = seller_location[0]
                        seller_location_district = None
                        seller_location_city = seller_location[1][1:]
                    elif len(seller_location) == 1:
                        seller_location_country = seller_location[0]
                        seller_location_district, seller_location_city = None, None

                    tag_album = soup.find_all("div", class_="album_item")
                    if tag_album != [] and tag_album[-1].h3 != None and tag_album[-1].h3.a != None:
                        collection = tag_album[-1].h3.a.text
                        url_collection = self.MAIN_URL + tag_album[-1].h3.a["href"]
                        if "/cards/" not in url_collection:
                            collection, url_collection = None, None
                    else:
                        collection, url_collection = None, None

                    # Достаем даты открытия и закрытия лота
                    tag_time = soup.find_all("div", {"style": re.compile("padding-top: 5px")})
                    date_start_txt = tag_time[0].text
                    date_start = date_start_txt.split("\xa0")
                    date_start[1] = self.MONTH_TO_NUM[date_start[1]]
                    if len(date_start) == 3:
                        date_start.insert(2, str(datetime.datetime.now().year))
                    date_start_day = date_start[0]
                    date_start_month = date_start[1]
                    date_start_year = date_start[2]
                    date_start_time = date_start[3]

                    date_end_txt = tag_time[1].text[1:-8]
                    date_end = date_end_txt.split("\xa0")
                    date_end[1] = self.MONTH_TO_NUM[date_end[1]]
                    if len(date_end) == 3:
                        date_end.insert(2, str(datetime.datetime.now().year))
                    date_end_day = date_end[0]
                    date_end_month = date_end[1]
                    date_end_year = date_end[2]
                    date_end_time = date_end[3]

                    dct = {"title": title, "url": url, "subject": subject, "theme": theme, "lot_type": lot_type,
                           "status": lot_status, "is_bet_made": is_bet_made, "collection": collection,
                           "url_collection": url_collection, "date_start_day": date_start_day,
                           "date_start_month": date_start_month, "date_start_year": date_start_year,
                           "date_start_time": date_start_time, "seller_nickname": seller_nickname,
                           "seller_url": seller_url, "seller_location_city": seller_location_city,
                           "seller_location_district": seller_location_district,
                           "seller_location_country": seller_location_country, "initial_price": initial_price,
                           "last_price": last_price, "last_price_author": last_price_author,
                           "url_last_buyer": url_last_buyer, "date_end_day": date_end_day,
                           "date_end_month": date_end_month, "date_end_year": date_end_year,
                           "date_end_time": date_end_time}
                    df = df.append(dct, ignore_index=True)
                    collection_upper = None if collection == None else collection.upper()
                    df_upper = df_upper.append({"title": title.upper(), "collection": collection_upper},
                                               ignore_index=True)

                    self.df = self.df.append(dct, ignore_index=True)
                    self.df_upper = self.df_upper.append({"title": title.upper(), "collection": collection_upper},
                                                         ignore_index=True)

                    if not json_written and not is_closed:
                        json_written = True
                        self.info["first_open_lot_csv_id"] = passed_pages + self.info["lots_amount"]
                        self.info["first_open_lot_url_id"] = i

                    passed_pages += 1

                    if passed_pages % self.csv_batch == 0:
                        df.to_csv(self.csv_path, sep=";", mode="a", header=False, index=False)
                        df = pd.DataFrame(columns=self.COL_NAMES)
                        df_upper.to_csv(self.upper_csv_path, sep=";", mode="a", header=False, index=False)
                        df_upper = pd.DataFrame(columns=["title", "collection"])

            except Exception:
                self.info["unparsed_pages"].append(url)

        self.info["lots_amount"] += passed_pages

        df.to_csv(self.csv_path, sep=";", mode="a", header=False, index=False)
        df_upper.to_csv(self.upper_csv_path, sep=";", mode="a", header=False, index=False)

        with open(self.json_path, "w") as f:
            json.dump(self.info, f)

    # Т.к. какие-то лоты могли закрыться, надо обновить существующие записи
    def __update_downloaded(self, chat_id=None):
        json_updated = False
        # После создания базы, мы запомнили id первого открытого лота. Обновлять существующие записи имеет смысл
        # начиная с этого лота и до конца, потому что все лоты до него закрыты и свою информацию уже не поменяют
        first, last = self.info.get("first_open_lot_csv_id", len(self.df)), len(self.df)
        rng = tqdm(range(first, last)) if chat_id == None else tq(range(first, last), token=self.token, chat_id=chat_id)

        for i in rng:
            # Если лот закрыт, то информацию о себе уже не поменяет, пропускаем
            if self.df.iloc[i]["status"] == "Открыт":
                try:
                    url = self.df.iloc[i]["url"]
                    response = requests.get(url)
                    soup = BeautifulSoup(response.content, "html.parser")

                    if response.status_code != 200:
                        self.df.loc[i, "status"] = "Удален"
                        continue

                    # Обновляем status
                    tag_closed = soup.find("div", id=re.compile("auction_bid_countdown"))
                    is_closed = "Дата и время окончания" in tag_closed.text
                    lot_status = is_closed * "Закрыт" + (not is_closed) * "Открыт"
                    self.df.loc[i, "status"] = lot_status

                    # Обновляем информацию про первый открытый лот в json
                    if not json_updated and not is_closed:
                        json_updated = True
                        self.info["first_open_lot_csv_id"] = i
                        self.info["first_open_lot_url_id"] = int(url[39:-1])

                    is_bet_made = self.df.iloc[i]["is_bet_made"]
                    tag_auction = soup.find("div", {"style": re.compile("float: left; width: 50%")})
                    if not is_bet_made and self.df.iloc[i]["lot_type"] != "Объявление":
                        # Обновляем initial_price и is_bet_made
                        is_bet_made = "Начальная ставка" not in tag_auction.text

                    # В is_bet_made актуальный статус

                    # Обновляем всю инфу по последней ставке
                    # Если ставка все-таки не сделана, то инфа не меняется
                    if is_bet_made:
                        if not self.df.iloc[i]["is_bet_made"]:
                            initial_price = tag_auction.contents[1].find_all("div")[-1].b.text
                            self.df.loc[i, "initial_price"] = initial_price

                        tag_last_bet = tag_auction.contents[1].find_all("div", {"style": re.compile("margin-bottom")})[
                            -1].next_sibling
                        if "Контрольное время" in tag_last_bet.text:
                            tag_last_bet = tag_last_bet.next_sibling

                        last_price = tag_last_bet.b.text
                        last_price_author = tag_last_bet.a.text
                        url_last_buyer = self.MAIN_URL + tag_last_bet.a["href"]
                        self.df.loc[i, "last_price"] = last_price
                        self.df.loc[i, "last_price_author"] = last_price_author
                        self.df.loc[i, "url_last_buyer"] = url_last_buyer

                except Exception:
                    pass

        try:
            self.df.to_csv(self.csv_path, sep=";", header=self.COL_NAMES, index=False)
        except Exception:
            self.df.to_csv(self.csv_path[:-4] + "_retry.csv", sep=";", header=self.COL_NAMES, index=False)
            if os.path.isfile(self.csv_path):
                os.remove(self.csv_path)

        return json_updated

    # Подгрузка ЕЩЕ НЕ записанных лотов
    def __download_new(self, json_updated, chat_id=None):

        now = datetime.datetime.now()
        self.info["last_lot_parse_date"] = "{}:{} {}.{}.{}".format(now.hour, now.minute, now.day, now.month, now.year)

        # Узнаем, какой номер у последнего на момент обновления лота
        last_lot_url_id = max(self.last_lot_url_id_now(),
                              self.info["last_lot_url_id"])  # на случай, если не сможет выпарсить url последнего лота

        self.__parse_to_csv(self.info["last_lot_url_id"] + 1, last_lot_url_id, json_updated, chat_id)
        lots_updated = last_lot_url_id - self.info["last_lot_url_id"]

        # Обновляем информацию про последний лот в json
        self.info["last_lot_url_id"] = last_lot_url_id
        with open(self.json_path, "w") as f:
            json.dump(self.info, f)

        return (
            self.info["last_lot_parse_date"], self.MAIN_URL + "/auction/post{}/".format(last_lot_url_id), lots_updated)

    def update(self, chat_id=None):
        json_updated = self.__update_downloaded(chat_id)
        return self.__download_new(json_updated, chat_id)

    # Фильтрация

    # Парсинг фильтров из запроса
    def __to_filters(self, text):
        try:
            words = text.split(" ")
            if not (words[0] == "&" or words[0] == "|"):
                msg = "Метка операции может быть только & или |, в самом начале (перед ней не должно быть пробела). "
                msg += "Проверьте правильность написания"
                return (False, msg)
            curr_filter = {"operation": words[0]}  # словарь распарсенных фильтров
            for col_ in words[1:]:
                col = col_.upper()
                if "СТАВК" in col:
                    curr_filter["is_bet_made"] = bool(int(col[-1]))
                elif "СТАТУСЛ" in col:
                    curr_filter["status"] = (self.DECODE_STATUS[col[-1]], col[0] != "!")
                elif "ТИП" in col:
                    curr_filter["lot_type"] = (self.DECODE_LOT_TYPE[col[-1]], col[0] != "!")
                elif "ПРЕДМ" in col:
                    curr_filter["subject"] = (self.DECODE_SBJ[col[-1]], col[0] != "!")
                elif "КАТЕГ" in col:
                    curr_filter["theme"] = (self.DECODE_THEME[col[-2:]], col[0] != "!")
                elif "ЗАГОЛ" in col:
                    curr_filter["title"] = (col.split("=")[1].split("+"), col[0] != "!")
                elif "КОЛЛЕК" in col:
                    curr_filter["collection"] = (col.split("=")[1].split("+"), col[0] != "!")
                elif "ПРОДАВЕ" in col:
                    curr_filter["seller_nickname"] = (col_.split("=")[1], col[0] != "!")
                elif "НЕРАНЬШ" in col or "НЕРАНЕЕ" in col:
                    curr_filter["not_earlier"] = col.split("=")[1]
                elif "НЕПОЗДНЕ" in col or "НЕПОЗЖ" in col:
                    curr_filter["not_later"] = col.split("=")[1]
                elif "СОРТИРОВАТЬ" in col:
                    curr_filter["sort_by"] = self.DECODE_SORT_BY[col.split("=")[1]]
                elif "МОИФИЛЬТРЫ" in col:
                    curr_filter["my_filters"] = col_.split("=")[1].split("+")
                elif "ПОКУПАТ" in col:
                    curr_filter["last_price_author"] = (col_.split("=")[1], col[0] != "!")
                elif col != "":
                    msg = "Не могу понять фильтр " + col_ + ". Проверьте соответствие правилам фильтрации /howfilter"
                    return (False, msg)

            return (True, curr_filter)

        except Exception:
            msg = "Не удалось распарсить запрос. Проверьте соответствие правилам фильтрации /howfilter"
            return (False, msg)

    @staticmethod
    def index_to_select_from(df, operation):
        return set(df.index) if operation == "&" else set()

    @staticmethod
    def join(s1, s2, operation):
        if operation == "&":
            s1 &= s2
        else:
            s1 |= s2

    # Смотрим, какие фильтры создал пользователь с id=user_id
    def __read_user_filters(self, user_id):
        user_filters_path = "{}/user_{}_filters.json".format(self.dir_path + "/users_filters", user_id)
        if os.path.isfile(user_filters_path):
            with open(user_filters_path, "r") as f:
                user_filters = json.load(f)
            return user_filters
        return {}

    # По распарсенному запросу фильтруем базу
    def __select_index(self, filter_dct, df, user_filters):
        from_index = df.index
        operation = filter_dct["operation"]
        selected_inds = self.index_to_select_from(df, operation)

        # Сначала обрабатываем "простые" фильтры, т.е. не те, которые создал пользователь
        for col in filter_dct:
            if col == "operation" or col == "sort_by" or col == "my_filters":
                continue

            elif col == "subject" or col == "theme" or col == "lot_type" or col == "status":
                local_inds = set(df[(df[col] == filter_dct[col][0]) == filter_dct[col][1]].index)

            elif col == "title" or col == "collection":
                upper_df = self.df_upper.loc[list(from_index)]
                for word in filter_dct[col][0]:
                    upper_df = upper_df[upper_df[col].str.contains(word) == True]
                if filter_dct[col][1]:
                    local_inds = set(df.index) & set(upper_df.index)
                else:
                    local_inds = set(df.index) - set(upper_df.index)

            elif col == "seller_nickname" or col == "last_price_author":
                local_inds = set(df[(df[col] == filter_dct[col][0]) == filter_dct[col][1]].index)

            elif col == "not_earlier" or col == "not_later":
                day_s, month_s, year_s = filter_dct[col].split(".")
                day, month, year = int(day_s), int(month_s), int(year_s)
                df_ = df[:]
                if col == "not_earlier":
                    df_ = df_[df_["date_end_year"] >= year]
                    df_ = df_[df_["date_end_month"] >= month]
                    local_inds = set(df_[df_["date_end_day"] >= day].index)
                if col == "not_later":
                    df_ = df_[df_["date_end_year"] <= year]
                    df_ = df_[df_["date_end_month"] <= month]
                    local_inds = set(df_[df_["date_end_day"] <= day].index)

            else:
                local_inds = set(df[df[col] == filter_dct[col]].index)

            self.join(selected_inds, local_inds, operation)

            if operation == "&":
                df = df.loc[list(selected_inds)]
                from_index = df.index

        # Обрабатываем пользовательские фильтры (если они есть в запросе)
        for my_filter in filter_dct.get("my_filters", []):
            if my_filter not in user_filters:
                msg = "Запрашиваемого фильтра " + my_filter + " нет в базе ☹️ Проверьте правильность написания. "
                msg += "Показать список существующих пользовательских фильтров /showfilters"
                return False, msg

            success, result = self.__select_index(user_filters[my_filter][0], df[:], user_filters)
            if not success:
                return success, result

            self.join(selected_inds, result, operation)
            if operation == "&":
                df = df.loc[list(selected_inds)]
                from_index = df.index

        return True, selected_inds

    def __select(self, dct, user_id):
        try:
            df = self.df[:]
            if len(dct) == 1 or (len(dct) == 2 and "sort_by" in dct):  # если запрос пустой или только на сортировку
                pass
            else:
                user_filters = self.__read_user_filters(user_id)
                success, result = self.__select_index(dct, df, user_filters)
                if not success:
                    return success, result
                df = df.loc[list(result)]

            # Сортируем, если есть такой запрос
            if "sort_by" in dct and dct["sort_by"] == "index":
                df.sort_index(inplace=True)
            elif "sort_by" in dct:
                df.sort_values(dct["sort_by"], inplace=True, na_position="first")

            return True, df
        except Exception:
            msg = "Что-то пошло не так. Проверьте корректность запроса. Искомые подстроки не должны "
            msg += "совпадать со служебными словами фильтрации. Команда /howfilter расскажет о ее правилах"
            return False, msg

    # Проверяем, закреплен ли за нашей базой бот
    def __check_from_telegram(self, user_id):
        assert self.token != "", "Этот функционал доступен только через Telegram. К объекту не привязан ни один бот"
        msg = "Этот функционал доступен только через Telegram. Идентификатора чата, в который будут присылаться "
        msg += "результаты, нет или он недопустимого типа"
        assert type(user_id) == int, msg

    def filter_(self, text, user_id):
        self.__check_from_telegram(user_id)
        ans = self.__to_filters(text)
        if not ans[0]:  # если фильтрация завершилась ошибкой
            return ans
        curr_filters = ans[1]
        result = self.__select(curr_filters, user_id)
        return result

    # Создаем новый пользовательский фильтр
    def create_new_filter(self, text, user_id):
        self.__check_from_telegram(user_id)
        try:
            users_filters_dir_path = "{}/users_filters".format(self.dir_path)
            user_filters_path = "{}/user_{}_filters.json".format(users_filters_dir_path, user_id)

            if not os.path.isdir(users_filters_dir_path):
                os.mkdir(users_filters_dir_path)

            if os.path.isfile(user_filters_path):
                with open(user_filters_path, "r") as f:
                    user_filters = json.load(f)
            else:
                user_filters = {}

            words = text.split(" ")
            filter_name = words[0]
            if filter_name in user_filters:
                return "Фильтр с таким именем уже существует. Он запрашивает\n*" + user_filters[filter_name][1] + "*"

            to_parse = " ".join(words[1:])
            if "сортировать" in to_parse:
                return "Нельзя создавать пользовательские фильтры с сортировкой 🙅‍♂️"

            success, result = self.__to_filters(to_parse)
            if not success:
                return result

            user_filters[filter_name] = (result, to_parse)
            with open(user_filters_path, "w") as f:
                json.dump(user_filters, f)
            return "Фильтр успешно создан"

        except Exception:
            msg = "Не удалось создать фильтр. Проверьте корректность запроса: между /newfilter, именем фильтра "
            msg += "и символом операции (& или |) должно быть ровно по одному пробелу. Текст фильтрации также "
            msg += "должен быть корректен, /howfilter подскажет"
            return msg

    # Удаляем пользовательский фильтр
    def delete_filter(self, filter_name, user_id):
        self.__check_from_telegram(user_id)
        user_filters_path = "{}/user_{}_filters.json".format(self.dir_path + "/users_filters", user_id)
        if os.path.isfile(user_filters_path):
            with open(user_filters_path, "r") as f:
                user_filters = json.load(f)
            if filter_name not in user_filters:
                msg = "Такой фильтр еще не был создан 😐 Убедитесь, что до и "
                msg += "после его названия нет незначащих пробелов"
                return msg
            user_filters.pop(filter_name)
            with open(user_filters_path, "w") as f:
                json.dump(user_filters, f)
            return "Фильтр успешно удален 👍"
        return "Вы еще не создали ни одного фильтра 🤷‍"


if __name__ == "__main__":
    LastStickerStat(sys.argv[1])