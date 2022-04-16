from telebot.async_telebot import AsyncTeleBot
from telebot import apihelper
import asyncio
import io

import constants
from dbhandler import dbHandler
from markups import markup as mk

bot = AsyncTeleBot(constants.APIKEY, parse_mode=None)
db = dbHandler(constants.DBPARAMS)
apihelper.SESSION_TIME_TO_LIVE = 300
stack = {}
rolemapping = {'user':'пользователь','admin':'администратор','owner':'владелец'}

def stackFilter(message, term, mustbedigit = False):
    if mustbedigit and not message.text.isdigit:
        return False
    if not stack.get(message.chat.id, False):
        return False
    return stack[message.chat.id].get(term, False)

async def csvLoadSender(idUser, loadSource, callData):
    try:
        period = int(callData[12:])
        load = db.ex(f"SELECT date_trunc('minute', timedate), employee.name, amount, info FROM {loadSource} JOIN employee ON employee.id = person WHERE timedate >= NOW()::date - INTEGER '%s' ", (period,))
    except ValueError:
        load = db.ex(f"SELECT date_trunc('minute', timedate), employee.name, amount, info FROM {loadSource} JOIN employee ON employee.id = person")
    if not load:
        await bot.send_message(idUser, 'Записей за данный период не найдено')
    else:
        load = '\n'.join([','.join([str(obj) for obj in item]) for item in load])
        f = io.StringIO('Время,Сотрудник,Сумма,Информация\n'+load)
        await bot.send_document(idUser, f, visible_file_name=f'{loadSource}.csv')

@bot.callback_query_handler(func=lambda call: True)
async def callbackQuery(call):
    if call.data.startswith('auth_'):
        data = call.data.split('_')
        db.ex('INSERT INTO users(handle, chatid, role) VALUES (%s, %s, %s) ON CONFLICT (chatid) DO UPDATE SET role = %s WHERE users.chatid = %s', (data[1], int(data[2]), data[3], data[3], int(data[2])))
        await bot.send_message(data[2], f'Ваши привилегии обновлены\nНовая роль: {rolemapping[data[3]]}\n/lk для перехода в личный кабинет')
        await bot.send_message(data[-1], 'Роль успешно обновлена')
    elif call.data == "adAuto":
        await adminAutoList(call)
    elif call.data == "adAutoAdd":
        stack[call.from_user.id]['addingAuto'] = True
        stack[call.from_user.id]['addingAutoName'] = None
        stack[call.from_user.id]['addingAutoColor'] = None
        await bot.send_message(call.from_user.id, 'Добавляем автомобиль в базу\nВведите название автомобиля')
    elif call.data == "endAutoAdd":
        stack[call.from_user.id]['addingAuto'] = False
        await bot.send_message(call.from_user.id, 'Добавление закончено\n/lk для входа в личный кабинет')
    elif call.data == "adAutoDelete":
        await bot.send_message(call.from_user.id, 'Введите номер автомобиля, который желаете удалить из базы')
        stack[call.from_user.id]['deletingAuto'] = True
    elif call.data == "endAutoDelete":
        stack[call.from_user.id]['deletingAuto'] = False
        await bot.send_message(call.from_user.id, 'Удаление автомобилей закончено\n/lk для входа в личный кабинет')
    elif call.data == "adEmployee":
        await adminEmployeeList(call)
    elif call.data == "adEmployeeAdd":
        await bot.send_message(call.from_user.id, 'Добавляем сотрудника в базу\nВведите имя')
        stack[call.from_user.id]['addingEmployee'] = True
        stack[call.from_user.id]['addingEmployeeName'] = None
        stack[call.from_user.id]['addingEmployeeCoeff'] = None
    elif call.data == "endEmployeeAdd":
        stack[call.from_user.id]['addingEmployee'] = False
        await bot.send_message(call.from_user.id, 'Добавление закончено\n/lk для входа в личный кабинет')
    elif call.data == "adEmployeeDelete":
        await bot.send_message(call.from_user.id, 'Введите номер сотрудника, которого желаете удалить из базы')
        stack[call.from_user.id]['deletingEmployee'] = True
    elif call.data == "endEmployeeDelete":
        stack[call.from_user.id]['deletingEmployee'] = False
        await bot.send_message(call.from_user.id, 'Удаление сотрудников закончено\n/lk для входа в личный кабинет')
    elif call.data == "adExpenses":
        await bot.send_message(call.from_user.id, 'Выберите период выгрузки расходов', reply_markup=mk.createMarkup(2, ['24 часа', 'Неделя', 'Месяц', 'Все время'], ['loadExpenses1', 'loadExpenses7', 'loadExpenses30', 'loadExpensesAll']))
    elif call.data.startswith('loadExpenses'):
        await csvLoadSender(call.from_user.id, 'expenses', call.data)
    elif call.data == "adIncome":
        await bot.send_message(call.from_user.id, 'Выберите период выгрузки доходов', reply_markup=mk.createMarkup(2, ['24 часа', 'Неделя', 'Месяц', 'Все время'], ['loadIncome1', 'loadIncome7', 'loadIncome30', 'loadIncomeAll']))
    elif call.data.startswith('loadIncome'):
        await csvLoadSender(call.from_user.id, 'incomes', call.data)

async def adminAutoList(call):
    carList = db.ex('SELECT * FROM auto')
    if carList:
        carList = '\n'.join([' '.join([str(obj) for obj in item]) for item in carList])
    else:
        carList = 'Список авто пуст'
    await bot.send_message(call.from_user.id, carList, reply_markup=mk.createMarkup(2, ['Добавить', 'Удалить'], ['adAutoAdd', 'adAutoDelete']))

@bot.message_handler(func=lambda message: stackFilter(message, 'addingAuto'))
async def addingAuto(message):
    if not stack[message.chat.id]['addingAutoName']:
        stack[message.chat.id]['addingAutoName'] = message.text
        await bot.send_message(message.chat.id, 'Теперь введите цвет машины')
    elif not stack[message.chat.id]['addingAutoColor']:
        stack[message.chat.id]['addingAutoColor'] = message.text
        await bot.send_message(message.chat.id, 'Теперь введите номерной знак машины')
    else:
        db.ex('INSERT INTO auto(name, color, licensenum) VALUES (%s, %s, %s)', param=(stack[message.chat.id]['addingAutoName'], stack[message.chat.id]['addingAutoColor'], message.text))
        await bot.send_message(message.chat.id, 'Готово! Машина добавлена в базу', reply_markup=mk.createMarkup(2, ['Добавить еще', 'Закончить'], ['adAutoAdd', 'endAutoAdd']))

@bot.message_handler(func=lambda message: stackFilter(message, 'deletingAuto', mustbedigit = True))
async def autoDeleter(message):
    db.ex('DELETE FROM auto WHERE id = %s', param=(int(message.text),))
    await bot.send_message(message.chat.id, f'Машина {message.text} удалена из базы', reply_markup=mk.createMarkup(2, ['Удалить еще', 'Закончить'], ['adAutoDelete', 'endAutoDelete']))

async def adminEmployeeList(call):
    employeeList = db.ex('SELECT id, name, coeff FROM employee WHERE deleted IS NOT TRUE')
    if employeeList:
        employeeList = '\n'.join([' '.join([str(obj) for obj in item]) for item in employeeList])
    else:
        employeeList = 'Список сотрудников пуст'
    await bot.send_message(call.from_user.id, employeeList, reply_markup=mk.createMarkup(2, ['Добавить', 'Удалить'], ['adEmployeeAdd', 'adEmployeeDelete']))

@bot.message_handler(func=lambda message: stackFilter(message, 'addingEmployee'))
async def addingEmployee(message):
    if not stack[message.chat.id]['addingEmployeeName']:
        stack[message.chat.id]['addingEmployeeName'] = message.text
        await bot.send_message(message.chat.id, 'Теперь введите коэффициент зарплаты для сотрудника (введите 1, чтобы оставить сотрудника без коэффициента)')
    else:
        try:
            coeff = float(message.text)
        except ValueError:
            await bot.send_message(message.chat.id, 'Число введено неверно, попробуйте еще раз\nДробное число нужно вводить с точкой: 1.5')
            return
        db.ex('INSERT INTO employee(name, coeff) VALUES (%s, %s)', param=(stack[message.chat.id]['addingEmployeeName'], message.text))
        await bot.send_message(message.chat.id, 'Готово! Сотрудник добавлен в базу', reply_markup=mk.createMarkup(2, ['Добавить еще', 'Закончить'], ['adEmployeeAdd', 'endEmployeeAdd']))

@bot.message_handler(func=lambda message: stackFilter(message, 'deletingEmployee', mustbedigit = True))
async def deletingEmployee(message):
    db.ex('UPDATE employee SET deleted = True WHERE id = %s', param=(int(message.text),))
    await bot.send_message(message.chat.id, f'Сотрудник {message.text} удален из базы', reply_markup=mk.createMarkup(2, ['Удалить еще', 'Закончить'], ['adEmployeeDelete', 'endEmployeeDelete']))

@bot.message_handler(commands=['dbtest'])
async def testHandler(message):
    await bot.send_message(message.chat.id, db.ex('SELECT * FROM test;'))

@bot.message_handler(func=lambda message: message.text in ['/authuser', '/authadmin', '/authowner'])
async def auth(message):
    role = message.text[5:]
    for owner in db.ex("SELECT chatid FROM users WHERE role = 'owner'"):
        await bot.send_message(owner[0], f'Новый запрос на авторизацию пользователя от @{message.chat.username}\nЗапрашиваемая роль: {rolemapping[role]}', reply_markup=mk.createMarkup(1, ['Авторизовать'],[f'auth_{message.chat.username}_{message.chat.id}_{role}_{owner[0]}']))

@bot.message_handler(commands=['lk'])
async def messageHandler(message):
    stack[message.chat.id] = {}
    roleCheck = db.ex('SELECT role FROM users WHERE chatid = %s', ())
    await bot.send_message(message.chat.id, "Личный кабинет администратора", reply_markup=mk.createMarkup(2, ['Автомобили', 'Сотрудники', 'Затраты', 'Доходы'], ['adAuto', 'adEmployee', 'adExpenses', 'adIncome']))

def main():
    asyncio.run(bot.polling())

if __name__ == '__main__':
    main()
