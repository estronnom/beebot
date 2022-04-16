from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

class markup():
    @staticmethod
    def createMarkup(rows, labels, datas):
        markup = InlineKeyboardMarkup()
        markup.row_width = rows
        buttons = [InlineKeyboardButton(label, callback_data=data) for label, data in zip(labels,datas)]
        markup.add(*buttons)
        return markup
