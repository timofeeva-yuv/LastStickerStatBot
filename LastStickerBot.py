import logging
import os
import sys
import tarfile
import telebot
import telegram
from LastStickerStat import *

with open("last-sticker-bot-token.txt", "r") as f:
    token = f.read()
stat = LastStickerStat(sys.argv[1], token)

with open("bot_config.json", "r") as f:
    bot_config = json.load(f)

bot = telebot.TeleBot(token)
is_confirmed = {}  # Например, is_confirmed[id]["show_links_confirmed"] == True, значит пользователь
# подтвердил, что хочет вызвать команду /links (в данном случае ее)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


# Делаем из однозначного числа двухзначное добавлением незначащего нуля. Нужно для вывода даты-времени в привычном
# виде, т.е. не 5:1, а 05:01
def double_digit(number):
    if len(number) == 1:
        number = "0" + number
    return number


# Выводим дату-время в привычном виде (с незначащими нулями)
def prettify_datetime(datetime):
    datetime_lst = datetime.split(" ")
    time_lst = datetime_lst[0].split(":")
    date_lst = datetime_lst[1].split(".")
    time = double_digit(time_lst[0]) + ":" + double_digit(time_lst[1])
    date = double_digit(date_lst[0]) + "." + double_digit(date_lst[1]) + "." + date_lst[2]
    datetime = time + " " + date
    return datetime


# Создаем csv файл с отфильтрованными данными
def create_filtered_data(path, df):
    if os.path.isfile(path):
        number = 1
        while os.path.isfile(str(number) + path):
            number += 1
        path = str(number) + path
    df.to_csv(path, sep=";", index=False)
    return path


# Сбрасываем значения булевых переменных, отвечающих за то, было ли действие пользователя
# по той или иной команде, подтверждено (например, для удаления польз. фильтра, нужно подтверждение)
def reset_confirmations(user_id):
    global is_confirmed
    if user_id not in is_confirmed:
        is_confirmed[user_id] = {}
    is_confirmed[user_id]["delete_confirmed"] = (False, "")  # подтверждение удаления фильтра с конкретным названием
    is_confirmed[user_id]["show_links_confirmed"] = False
    is_confirmed[user_id]["delete_all_users_confirmed"] = False
    is_confirmed[user_id]["download_confirmed"] = False


# Обновляем файл bot_config, содержащий id админов и разрешенных пользователей
def rewrite_bot_config():
    global bot_config
    with open("bot_config.json", "w") as f:
        json.dump(bot_config, f)


# Архивируем файл и отправляем
def send_archived(file_path, user_id):
    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    bot.send_message(user_id, "Создаем архив и высылаем")

    archive_path = file_path + ".tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(file_path)

    bot.send_chat_action(user_id, action=telegram.ChatAction.UPLOAD_DOCUMENT)
    with open(archive_path, "rb") as f:
        bot.send_document(user_id, f)

    os.remove(archive_path)



# Если у пользователя еще нет прав доступа к боту, то он об этом оповещается и ему предлагается
# написать свой ник на сайте laststicker (чтобы админы понимали, что за человек, с какой историей на сайте)
# Админы оповещаются о попытке взаимодействия с ботом постороннего лица
@bot.message_handler(commands=['start'], func=lambda msg: msg.from_user.id not in bot_config["allowed_ids"])
def handle_unknown_start(message):
    global bot_config
    user_id = message.from_user.id
    user_name = message.from_user.username
    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    msg1 = "Бот находится в разработке. Напишите свой ник на сайте laststicker.ru, "
    msg1 += "чтобы разработчики понимали, кому этот бот интересен"
    bot.send_message(user_id, msg1)
    msg2 = "Неизвестный пользователь @{} (id = {}) взаимодействовал с ботом".format(user_name, user_id)
    for admin_id in bot_config["ADMIN_IDS"]:
        bot.send_message(admin_id, msg2)


# Если неизвестный ответил (скорее всего написал ник), это пересылается админам. Они проверяют все, что
# надо проверить, и решают давать права доступа новому пользователю или нет
@bot.message_handler(func=lambda msg: msg.from_user.id not in bot_config["allowed_ids"])
def handle_unknown(message):
    global bot_config
    user_id = message.from_user.id
    user_name = message.from_user.username
    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    bot.send_message(user_id, "Переслали ваше сообщение разработчикам 👌 Пока вам не дали доступ к функционалу бота")
    msg = "Пользователь @{} (id = {}) прислал сообщение. Возможно, это ник на laststicker".format(user_name, user_id)
    for admin_id in bot_config["ADMIN_IDS"]:
        bot.send_message(admin_id, msg)
        bot.forward_message(admin_id, user_id, message.message_id)


# Даем доступ к боту
@bot.message_handler(commands=['adduser'])
def handle_add_user(message):
    user_id = message.from_user.id
    reset_confirmations(user_id)
    global bot_config
    try:
        new_user_id = int(message.text[len("/adduser "):])
        if user_id in bot_config["ADMIN_IDS"] and new_user_id not in bot_config["allowed_ids"]:
            bot_config["allowed_ids"].append(new_user_id)
            rewrite_bot_config()
            msg = "[Пользователю](tg://user?id={}) успешно дан доступ к боту. Оповестили его об этом 👌".format(
                new_user_id)
            bot.send_message(new_user_id, "Вам дали доступ к боту @LastStickerStatBot")
        elif user_id in bot_config["ADMIN_IDS"]:
            msg = "[Пользователю](tg://user?id={}) уже дан доступ к боту".format(new_user_id)
        else:
            msg = "Вы не админ, у вас нет полномочий раздавать права доступа к боту 😠"
    except Exception:
        msg = "Не удалось дать доступ пользователю к боту 😞 Проверьте правильность написания id. "
        msg += "Скорее всего до и/или после него есть лишние символы (пробелы/табуляция/переносы и т. д.)"
    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    bot.send_message(user_id, msg, parse_mode="Markdown")


# Отбираем доступ к боту
@bot.message_handler(commands=['deleteuser'])
def handle_delete_user(message):
    user_id = message.from_user.id
    reset_confirmations(user_id)
    global bot_config
    try:
        user_id_to_delete = int(message.text[len("/deleteuser "):])
        if user_id in bot_config["ADMIN_IDS"] and user_id_to_delete in bot_config["ADMIN_IDS"]:
            msg = "Вы не можете запретить доступ админу"
        elif user_id in bot_config["ADMIN_IDS"] and user_id_to_delete in bot_config["allowed_ids"]:
            bot_config["allowed_ids"].remove(int(message.text[len('adduser '):]))
            rewrite_bot_config()
            msg = "[Пользователь](tg://user?id={}) больше не может пользоваться ботом 👌".format(user_id_to_delete)
        elif user_id in bot_config["ADMIN_IDS"]:
            msg = "У [пользователя](tg://user?id={}) и не было доступа к боту".format(user_id_to_delete)
        else:
            msg = "Вы не админ, у вас нет полномочий отбирать права доступа к боту 😠"
    except Exception:
        msg = "Не удалось исключить пользователя из списка тех, кто может пользоваться ботом 😞 "
        msg += "Проверьте правильность написания id. Скорее всего до и/или после него есть лишние символы "
        msg += "(пробелы/табуляция/переносы и т. д.)"
    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    bot.send_message(user_id, msg, parse_mode="Markdown")


# Отбираем доступ у всех НЕ админов
@bot.message_handler(commands=['deleteallusers'])
def handle_delete_all_users(message):
    user_id = message.from_user.id
    global bot_config

    if user_id not in bot_config["ADMIN_IDS"]:
        bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
        bot.send_message(user_id, "Вы не админ, у вас нет полномочий отбирать права доступа к боту 😠")
        reset_confirmations(user_id)
        return

    global is_confirmed
    is_confirmed.setdefault(user_id, {"delete_all_users_confirmed": False})
    delete_all_users_confirmed = is_confirmed[user_id].setdefault("delete_all_users_confirmed", False)
    reset_confirmations(user_id)

    if not delete_all_users_confirmed:
        msg = "Вы уверены, что хотите запретить доступ к боту всем пользователям, кроме админов? "
        msg += "Если да, повторите команду /deleteallusers"
        is_confirmed[user_id]["delete_all_users_confirmed"] = True
    else:
        bot_config["allowed_ids"] = bot_config["ADMIN_IDS"][:]
        rewrite_bot_config()
        msg = "Успешно. Теперь доступы есть только у админов"
    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    bot.send_message(user_id, msg)


# Выдаем приветственную информацию
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    reset_confirmations(user_id)

    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    msg = "Добро пожаловать в бот *LastStickerStat*\!🥳🥳🥳🥳\nЗдесь мы анализируем статистику по "
    msg += "лотам сайта laststicker\.ru\n\nВот, что умеет бот \(/help\)"
    bot.send_message(user_id, msg, parse_mode='MarkdownV2')
    handle_help(message)


# Напоминаем, как пользоваться ботом (какие есть команды, что они делают)
@bot.message_handler(commands=['help'])
def handle_help(message):
    user_id = message.from_user.id
    reset_confirmations(user_id)
    global bot_config

    msg = "/info - показать размер (в МБ) .csv файла с базой, дату и время последнего обновления, " \
          "ссылку на последний имеющийся в базе лот\n"
    msg += "/links - показать url не распарсенных страниц (в этом списке будут форумные страницы, " \
           "т. к. они не представляют никакой полезной информации для анализа; но возможно случайно " \
           "туда попадет что-то содержательное)\n"
    msg += "/download - выслать файл .csv, где представлены записи всех лотов сайта до момента последнего обновления\n"
    msg += "/update - обновить базу лотов\n"
    msg += "/howfilter - показать, *как пользоваться фильтрацией* (обязательно к ознакомлению перед " \
           "первым использованием)\n"
    msg += "/filter ... - отфильтровать данные по запросу ...\n"
    msg += "/showfilters - показать список пользовательских фильтров\n"
    msg += "/newfilter _name_ ... - создать пользовательский фильтр с именем _name_ и запросом ... " \
           "*Нельзя создавать пользовательский фильтр с сортировкой!*\n"
    msg += "/deletefilter _name_ - удалить пользовательский фильтр с именем _name_"

    if user_id in bot_config["ADMIN_IDS"]:
        msg += "\n\n*ДЛЯ АДМИНОВ*:\n"
        msg += "/downloadall - скачать папку со всеми данными о базе: все .csv (основная база и " \
               "база верхнего регистра) и .json (папка с пользовательскими фильтрами и информация о " \
               "текущем состоянии базы) файлы\n"
        msg += "/adduser _id_ - дать пользователю с идентификатором _id_ доступ к боту\n"
        msg += "/deleteuser _id_ - запретить пользователю с идентификатором _id_ пользоваться ботом\n"
        msg += "/deleteallusers - отобрать доступ к боту у всех, кроме админов\n"
        msg += "/notify - отправить сообщение (в разметке Markdown) всем пользователям бота"

    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    bot.send_message(user_id, msg, parse_mode="Markdown")


# Выгружаем базу и всю информацию о ней и боте
@bot.message_handler(commands=['downloadall'])
def handle_download_all(message):
    user_id = message.from_user.id
    reset_confirmations(user_id)
    global bot_config

    if user_id not in bot_config["ADMIN_IDS"]:
        bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
        bot.send_message(user_id, "Вы не админ, у вас нет прав пользоваться этим функционалом 😟")
        return
    
    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    bot.send_message(user_id, "Создаем архив и высылаем")

    archive_path = stat.dir_path + ".tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        for root, dirs, files in os.walk(stat.dir_path):
            for file in files:
                tar.add(os.path.join(root, file))

    archive_size = os.path.getsize(archive_path)
    if archive_size >= (50 * 1024 * 1024):  # если файл больше 50 МБ, серверы Telegram не будут его отправлять
        bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
        msg = "❗️ Размер архива больше или равен 50 МБ, что превышает допустимый порог для отправки через серверы " \
              "Telegram ❗️ Пора установить Local API, чтобы эти ограничения снялись"
        bot.send_message(user_id, msg)
    else:
        bot.send_chat_action(user_id, action=telegram.ChatAction.UPLOAD_DOCUMENT)
        with open(archive_path, "rb") as f:
            bot.send_document(user_id, f)


# Выгружаем базу в csv файле
@bot.message_handler(commands=['download'])
def handle_download(message):
    user_id = message.from_user.id

    csv_size = os.path.getsize(stat.csv_path)
    if csv_size < (50 * 1024 * 1024):
        reset_confirmations(user_id)
        lots = stat.info["lots_amount"]
        datetime = prettify_datetime(stat.info["last_lot_parse_date"])
        fails = len(stat.info["unparsed_pages"])

        msg = "Всего лотов: {}".format(lots)
        msg += "\nНе распарсенных ссылок: " + str(fails)
        msg += "\nПоследнее обновление: " + datetime
        msg += "\nНаберите команду /update, если хотите обновить данные."

        bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
        bot.send_message(user_id, msg)

        bot.send_chat_action(user_id, action=telegram.ChatAction.UPLOAD_DOCUMENT)
        with open(stat.csv_path, "r") as f:
            bot.send_document(user_id, f)
    else:
        global is_confirmed
        is_confirmed.setdefault(user_id, {"download_confirmed": False})
        download_confirmed = is_confirmed[user_id].setdefault("download_confirmed", False)
        reset_confirmations(user_id)

        if not download_confirmed:
            is_confirmed[user_id]["download_confirmed"] = True
            msg = "❗️ Размер csv больше или равен 50 МБ, что превышает допустимый порог для отправки " \
                  "через серверы Telegram ❗️\n Хотите загрузить файл архивом? Если да, повторите команду /download"
            bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
            bot.send_message(user_id, msg)
        else:
            send_archived(stat.csv_path, user_id)


# Выводим список не распарсенных ссылок или выгружаем файл с такой информацией (если ссылок больше 15)
@bot.message_handler(commands=["links"])
def handle_links(message):
    user_id = message.from_user.id

    fails = stat.info["unparsed_pages"]
    global is_confirmed
    is_confirmed.setdefault(user_id, {"show_links_confirmed": False})
    show_links_confirmed = is_confirmed[user_id].setdefault("show_links_confirmed", False)
    reset_confirmations(user_id)

    if len(fails) <= 15:  # до 15 вкл. ссылок можем вывести в чат, иначе отправляем все в csv файле
        msg = "Ссылки, которые не удалось распарсить:"
        for url in fails:
            msg += "\n" + url
    elif not show_links_confirmed:
        msg = "Всего {} не распарсенных ссылки. Вы уверены, что хотите увидеть весь список? ".format(len(fails))
        msg += "Если да, то повторите команду /links и вышлем csv файл со списком"
        is_confirmed[user_id]["show_links_confirmed"] = True
    else:
        bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
        bot.send_message(user_id, "Создаем файл и высылаем")

        file_path = "unparsed_url.csv"
        pd.DataFrame(fails, columns=["unparsed_url"]).to_csv(file_path, index=False)

        bot.send_chat_action(user_id, action=telegram.ChatAction.UPLOAD_DOCUMENT)
        with open(file_path, "r") as f:
            bot.send_document(user_id, f)
        return

    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    bot.send_message(user_id, msg)


# Обновляем базу (если никто еще не начал это делать)
@bot.message_handler(commands=["update"], func=lambda msg: stat.upd_allowed)
def handle_update(message):
    user_id = message.from_user.id
    reset_confirmations(user_id)
    stat.upd_allowed = False

    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    bot.send_message(user_id, "Сначала обновим информацию по существующим записям, потом подгрузим новые")

    last_lot_parse_date, last_lot_url, pages = stat.update(user_id)
    stat.upd_allowed = True

    msg = "\nПоследний лот " + last_lot_url + " загружен в " + prettify_datetime(last_lot_parse_date)
    msg += "\nВсего новых лотов загружено: " + str(pages)

    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    bot.send_message(user_id, msg)


# Если кто-то уже обновляет базу, сообщаем об этом
@bot.message_handler(commands=["update"])
def handle_update_not_allowed(message):
    user_id = message.from_user.id
    reset_confirmations(user_id)

    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    bot.send_message(user_id, "В данный момент данные обновляются 🕞 Вы сможете повторно обновить их позднее")


# Выводим краткую информацию о текущем состоянии базы (размер базы в МБ, кол-во записей, дата
# последнего обновления и ссылку на последний лот
@bot.message_handler(commands=["info"])
def handle_info(message):
    user_id = message.from_user.id
    reset_confirmations(user_id)

    csv_size = round(os.path.getsize(stat.csv_path) / (1024 * 1024), 2)
    msg = "Размер csv файла: {} МБ\nВсего лотов: {}".format(csv_size, stat.info["lots_amount"])
    msg += "\nДата последнего обновления: "
    datetime = stat.info.get("last_lot_parse_date", "нет данных")
    if datetime != "нет данных":
        datetime = prettify_datetime(datetime)
    msg += datetime
    msg += "\nПоследний лот в базе: " + stat.MAIN_URL + "/auction/post" + str(stat.info["last_lot_url_id"]) + "/"

    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    bot.send_message(user_id, msg)


# Создаем новый пользовательский фильтр
@bot.message_handler(commands=["newfilter"])
def handle_new_filter(message):
    user_id = message.from_user.id
    reset_confirmations(user_id)

    if message.text == "/newfilter":  # если набрали /newfilter без аргументов
        bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
        msg = "Как пользоваться командой /newfilter\n\n"
        msg += "/newfilter _ИМЯ_ _ОПЕРАЦИЯ_ _{КЛЮЧЕВОЕ СЛОВО=ЗНАЧЕНИЕ}_\n\n"
        msg += "*Нельзя создавать пользовательский фильтр с сортировкой!* Помните, что между " \
               "/newfilter, _ИМЯ_ и _ОПЕРАЦИЯ_ должно быть по *одному пробелу*. "
        msg += "Список ключевых слов и их возможных значений можно посмотреть по команде /howfilter"
        bot.send_message(user_id, msg, parse_mode="Markdown")
        return

    request = message.text[len("/newfilter "):]

    msg = stat.create_new_filter(request, user_id)
    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    bot.send_message(user_id, msg, parse_mode="Markdown")


# Удаляем пользовательский фильтр
@bot.message_handler(commands=["deletefilter"])
def handle_delete_filter(message):
    user_id = message.from_user.id

    if message.text == "/deletefilter":  # если набрали /deletefilter без аргументов
        bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
        msg = "Как пользоваться командой /deletefilter\n\n"
        msg += "/deletefilter _ИМЯ_\n\n"
        msg += "Помните, что между /deletefilter и _ИМЯ_ должен быть *один пробел*. _ИМЯ_ " \
               "должно с точность до регистра посимвольно совпадать с названием удаляемого фильтра"
        bot.send_message(user_id, msg, parse_mode="Markdown")
        return

    global is_confirmed
    is_confirmed.setdefault(user_id, {"delete_confirmed": (False, "")})
    delete_confirmed = is_confirmed[user_id].setdefault("delete_confirmed", (False, ""))

    filter_name = message.text[len("/deletefilter "):]
    if not delete_confirmed[0] or delete_confirmed[1] != message.text:  # обязательное подтверждение удаления
        msg = "❗️ Удаление фильтра может привести к сбоям в дальнейшей работе бота, если на основе " \
              "этого фильтра созданы другие ❗️\nПосмотреть, как создавались фильтры /showfilters.\n" \
              "Если вы уверены в своих намерениях, повторите запрос символ в символ"
        reset_confirmations(user_id)
        is_confirmed[user_id]["delete_confirmed"] = (True, message.text)
    elif delete_confirmed[1] == message.text:
        msg = stat.delete_filter(filter_name, user_id)
        reset_confirmations(user_id)

    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    bot.send_message(user_id, msg)


# Выводим список созданных фильтров конкретного пользователя (у каждого пользователя свои)
@bot.message_handler(commands=["showfilters"])
def handle_show_filters(message):
    user_id = message.from_user.id
    reset_confirmations(user_id)

    user_filters_path = "{}/{}/user_{}_filters.json".format(stat.dir_path, "users_filters", user_id)
    if os.path.isfile(user_filters_path):
        msg = ""
        with open(user_filters_path, "r") as f:
            user_filters = json.load(f)

        if len(user_filters) != 0:
            for filter_name in user_filters:
                msg += "• <b>" + filter_name + "</b> ⟶ " + user_filters[filter_name][1] + "\n"
        else:
            msg += "Вы не создали еще ни одного фильтра 🤷‍"
    else:
        msg = "Вы не создали еще ни одного фильтра 🤷‍♀️"

    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    bot.send_message(user_id, msg, parse_mode='HTML')


# Фильтруем данные по запросу и высылаем результат (если >= 50 МБ, то архивируем и высылаем)
@bot.message_handler(commands=["filter"])
def handle_filter(message):
    user_id = message.from_user.id
    reset_confirmations(user_id)

    if message.text == "/filter":
        handle_howfilter(message)
        return

    request = message.text[len("/filter "):]

    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    bot.send_message(user_id, "Парсим запрос и фильтруем...")

    success, result = stat.filter_(request, user_id)  # Отправляем отфильтрованный срез базы или сообщаем об ошибке
    if not success:
        bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
        bot.send_message(user_id, result)
    else:
        bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
        bot.send_message(user_id,
                         "Фильтрация прошла успешно 😄 Количество удовлетворивших запросу лотов: {}\nРезультат:".format(
                             len(result)))

        date, t = str(datetime.datetime.now()).split(".")[0][:-3].split(" ")
        time = t[:2] + "-" + t[3:]
        filtered_name = "filtered_" + date + "_" + time + ".csv"
        filtered_path = create_filtered_data(filtered_name, result)

        filtered_size = os.path.getsize(filtered_path)
        if filtered_size < (54 * 1024 * 1024):
            bot.send_chat_action(user_id, action=telegram.ChatAction.UPLOAD_DOCUMENT)
            with open(filtered_path, "r") as f:
                bot.send_document(user_id, f)
        else:
            msg = "❗️ Размер csv больше или равен 50 МБ, что превышает допустимый порог для отправки " \
                  "через серверы Telegram ❗️\n Высылаем архивированный csv"
            bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
            bot.send_message(user_id, msg)
            send_archived(filtered_path, user_id)
        os.remove(filtered_path)


# Напомнить синтаксис запросов (как фильтровать)
@bot.message_handler(commands=["howfilter"])
def handle_howfilter(message):
    user_id = message.from_user.id
    reset_confirmations(user_id)

    msg = "Как писать запрос на фильтрацию данных 📊\n\n"
    msg += "В самом начале запроса всегда находится символ операции - *&* или *|*, " \
           "запрос на пересечение фильтров или объединение соответственно\n\n"
    msg += "Далее перечислены ключевые, они же служебные, слова (выделены жирным шрифтом) " \
           "и их возможные значения. Имейте в виду, что *значения не должны содержать (в качестве подстроки) " \
           "служебные слова*. Т.е. например, подзапрос _заголовок=предметные_ составлен некорректно, т.к. " \
           "*предм* - служебное слово, а значение _предметные_ содержит такую подстроку\n\n"
    msg += "*(!) Перед служебным словом означает возможность запроса с отрицанием значения по этому " \
           "ключевому слову*\n\n"
    msg += "(!)*статусл*ота:        о - открыт\n                                 з - закрыт\n" \
           "                                 у - удален\n\n"
    msg += "*ставк*а:                   0 - ставка не сделана\n                                 " \
           "1 - ставка сделана\n\n"
    msg += "(!)*тип*:                      а - Аукцион\n                                 " \
           "о - Объявление\n                                 с - Староформатное\n\n"
    msg += "(!)*предм*ет:            0 - Неопределено\n                                 " \
           "н - Наклейки\n                                 к - Карточки\n                                 " \
           "д - Другое\n\n"
    msg += "(!)*катег*ория:         дс - Другие виды спорта\n                                 " \
           "мк - Мультфильмы и кино\n                                 фн/фк - Футбольные наклейки/карточки\n" \
           "                                 хн/хк - Хоккейные наклейки/карточки\n                                 " \
           "пн/пк - Прочие наклейки/карточки\n                                 ки - ККИ\n\n"
    msg += "*сортировать*:       в - по времени создания лота\n                                 ц - по цене продажи\n" \
           "                                 к - по названию коллекции\n\n"
    msg += "(!)*продаве*ц: одно слово, регистр важен\n\n"
    msg += "(!)*покупат*ель: одно слово, регистр важен\n\n"
    msg += "*нераньш*е или *неранее*: дата в формате дд.мм.ггг (нераньше _по завершению_)\n\n"
    msg += "*непоздне*е или *непозж*е: дата в формате дд.мм.ггг (непозже _по завершению_)\n\n"
    msg += "(!)*коллек*ция: одно слово или слова, разделяемые знаком +; регистр неважен. " \
           "!коллекция={}+{}+... означает, найти коллекция={}+{}+... и выбросить эти записи из " \
           "результата (т.е. в названии коллекции не по отдельности, а *одновременно* не должно быть " \
           "перечисленных подстрок)\n\n"
    msg += "(!)*загол*овок: одно слово или слова, разделяемые знаком +; регистр неважен. " \
           "!заголовок={}+{}+... работает аналогично !коллекция={}+{}+..., см. выше\n\n"
    msg += "*моифильтры*: одно слово или слова, разделяемые знаком +; регистр важен\n\n"
    msg += "Примеры запросов:\n\n*| категория=мк сортировать=ц* ⟶ вывести лоты категории Мультфильмы " \
           "и кино и отсортировать по цене продажи (операция не важна, когда данные фильтруются по " \
           "одному ключу плюс, возможно, сортируются)\n\n"
    msg += "*& коллекция=поттер+panini открыт !продавец=dfyz* ⟶ вывести все лоты, в названии которых " \
           "есть слова поттер и panini (любого регистра), такие что их размещал не dfyz\n\n"
    msg += "*& !коллекция=поттер+panini открыт ставка=1* ⟶ вывести все открытые лоты, в которых сделана " \
           "ставка (получается, аукционы), такие что в названии коллекции *одновременно* нет двух слов - " \
           "поттер и panini (*только поттер или только panini в названии коллекции быть могут*)\n\n"
    msg += "*| моифильтры=ГПоткр+ГПзакр+ГПстар* ⟶ вывести объединение пользовательских фильтров ГПоткр, ГПзакр и ГПстар"
    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    bot.send_message(user_id, msg, parse_mode="Markdown")


# Разослать новость от имени разработчика о новой внедренной фиче всем пользователям бота
@bot.message_handler(commands=["notify"])
def handle_notify(message):
    user_id = message.from_user.id
    reset_confirmations(user_id)
    global bot_config

    if user_id not in bot_config["ADMIN_IDS"]:
        bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
        bot.send_message(user_id, "Вы не админ, у вас нет прав пользоваться этим функционалом 😟")
        return

    msg = "*Новости от разработчиков*\n\n"
    msg += message.text[len("/notify "):]
    for to_id in bot_config["allowed_ids"]:
        bot.send_message(to_id, msg, parse_mode="Markdown")


# Если не набрали не одну перечисленную команду
@bot.message_handler(func=lambda msg: True)
def handle_anything(message):
    user_id = message.from_user.id
    reset_confirmations(user_id)

    msg = "Вы не набрали ни одной известной боту команды. Посмотреть доступные /help"
    bot.send_chat_action(user_id, action=telegram.ChatAction.TYPING)
    bot.send_message(user_id, msg)


bot.infinity_polling()
