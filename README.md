# LastStickerStatBot
Инструмент для парсинга информации о лотах с сайта [laststicker.ru](https://www.laststicker.ru/)  
  

**Настоятельно рекомендую** заглянуть в [Tutorial.ipynb](./Tutorial.ipynb). Там все расписано очень подробно: про идею, функционал, возможности и т. д.  
  
Но если вкраце:  
- [data](./data) - папка с огромной предзаписанной базой лотов (400К+ записей)
- [LastStickerStat.py](./LastStickerStat.py) - файл с классом LastStickerStat для парсинга и фильтрации (функционал фильтрации доступен только через бот)
- [LastStickerBot.py](./LastStickerBot.py) - файл с функционалом бота
- [LastStickerScrapping.ipynb](./LastStickerScrapping.ipynb) - разведывательный файл. Туда лучше не заглядывать, там mess. Оставила для истории  
  
`python3 LastStickerStat.py dir_name` - если папка dir_name (с базой) существует, то ничего не делает; иначе в эту папку выгружает все 400К+ записей с сайта  
`python3 LastStickerBot.py dir_name` - аналогично, но при этом "прикрепляется" к боту и открывает новый функционал для работы с базой через Телеграм (см. [Tutorial.ipynb](./Tutorial.ipynb)). Перед использованием положите токен вашего бота в [last-sticker-bot-token.txt](./last-sticker-bot-token.txt), и ваш персональный Телеграм id в [bot_config.ipynb](./bot_config.ipynb) в списки `allowed_ids` и `ADMIN_IDS`
