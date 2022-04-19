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

def clearUserStack(id):
    stack[id] = {}

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

async def insertDigit(message, direction, note, func):
    try:
        digit = func(message.text.replace(',' , '.'))
        stack[message.chat.id][direction] = digit
        print(f'{direction} is {digit}')
        await bot.send_message(message.chat.id, note)
    except ValueError:
        await bot.send_message(message.chat.id, 'Число введено некорректо, попробуйте еще раз')

@bot.callback_query_handler(func=lambda call: True)
async def callbackQuery(call):
    clearUserStack(call.from_user.id)
    if call.data.startswith('auth_'):
        data = call.data.split('_')
        db.ex('INSERT INTO users(handle, chatid, role) VALUES (%s, %s, %s) ON CONFLICT (chatid) DO UPDATE SET role = %s WHERE users.chatid = %s', (data[1], int(data[2]), data[3], data[3], int(data[2])))
        await bot.send_message(data[2], f'Ваши привилегии обновлены\nНовая роль: {rolemapping[data[3]]}\n/office для перехода в личный кабинет')
        await bot.send_message(data[-1], 'Роль успешно обновлена')
    elif call.data == "adAuto":
        await bot.send_message(call.from_user.id, 'Список авто:\n' + getAutoList(), reply_markup=mk.createMarkup(2, ['Добавить', 'Удалить'], ['adAutoAdd', 'adAutoDelete']))
    elif call.data == "adAutoAdd":
        stack[call.from_user.id]['addingAuto'] = True
        stack[call.from_user.id]['addingAutoName'] = None
        stack[call.from_user.id]['addingAutoColor'] = None
        await bot.send_message(call.from_user.id, 'Добавляем автомобиль в базу\nВведите название автомобиля')
    elif call.data == "endAutoAdd":
        stack[call.from_user.id]['addingAuto'] = False
        await bot.send_message(call.from_user.id, 'Добавление закончено\n/office для входа в личный кабинет')
    elif call.data == "adAutoDelete":
        await bot.send_message(call.from_user.id, 'Введите номер автомобиля, который желаете удалить из базы')
        stack[call.from_user.id]['deletingAuto'] = True
    elif call.data == "endAutoDelete":
        stack[call.from_user.id]['deletingAuto'] = False
        await bot.send_message(call.from_user.id, 'Удаление автомобилей закончено\n/office для входа в личный кабинет')
    elif call.data == "adEmployee":
        await bot.send_message(call.from_user.id, 'Список сотрудников:\n' + getEmployees(coeff = True), reply_markup=mk.createMarkup(2, ['Добавить', 'Удалить'], ['adEmployeeAdd', 'adEmployeeDelete']))
    elif call.data == "adEmployeeAdd":
        await bot.send_message(call.from_user.id, 'Добавляем сотрудника в базу\nВведите имя')
        stack[call.from_user.id]['addingEmployee'] = True
        stack[call.from_user.id]['addingEmployeeName'] = None
        stack[call.from_user.id]['addingEmployeeCoeff'] = None
    elif call.data == "endEmployeeAdd":
        stack[call.from_user.id]['addingEmployee'] = False
        await bot.send_message(call.from_user.id, 'Добавление закончено\n/office для входа в личный кабинет')
    elif call.data == "adEmployeeDelete":
        await bot.send_message(call.from_user.id, 'Введите номер сотрудника, которого желаете удалить из базы')
        stack[call.from_user.id]['deletingEmployee'] = True
    elif call.data == "endEmployeeDelete":
        stack[call.from_user.id]['deletingEmployee'] = False
        await bot.send_message(call.from_user.id, 'Удаление сотрудников закончено\n/office для входа в личный кабинет')
    elif call.data == "adExpenses":
        await bot.send_message(call.from_user.id, 'Выберите период выгрузки расходов', reply_markup=mk.createMarkup(2, ['24 часа', 'Неделя', 'Месяц', 'Все время'], ['loadExpenses1', 'loadExpenses7', 'loadExpenses30', 'loadExpensesAll']))
    elif call.data.startswith('loadExpenses'):
        await csvLoadSender(call.from_user.id, 'expenses', call.data)
    elif call.data == "adIncome":
        await bot.send_message(call.from_user.id, 'Выберите период выгрузки доходов', reply_markup=mk.createMarkup(2, ['24 часа', 'Неделя', 'Месяц', 'Все время'], ['loadIncome1', 'loadIncome7', 'loadIncome30', 'loadIncomeAll']))
    elif call.data.startswith('loadIncome'):
        await csvLoadSender(call.from_user.id, 'incomes', call.data)
    elif call.data == "userTask":
        stack[call.from_user.id]['creatingTask'] = True
        stack[call.from_user.id]['taskObject'] = None
        stack[call.from_user.id]['taskCar'] = None
        stack[call.from_user.id]['taskBuddy'] = None
        stack[call.from_user.id]['taskKm'] = None
        stack[call.from_user.id]['taskTime'] = None
        stack[call.from_user.id]['taskIncome'] = None
        stack[call.from_user.id]['taskExpenses'] = None
        lastObject = db.ex('SELECT id, object FROM task ORDER BY time DESC LIMIT 10')
        if not lastObject:
            queryText = 'Заполняем задачу\nДля начала введите название объекта:'
        else:
            lastObject = '\n'.join([' '.join([str(obj) for obj in item]) for item in lastObject])
            queryText = 'Заполняем задачу\nВведите название нового объекта или пришлите номер одного из представленных:\n\n' + lastObject
        await bot.send_message(call.from_user.id, queryText)
    elif call.data == "userIncome":
        pass

@bot.message_handler(func=lambda message: stackFilter(message, 'creatingTask') or message.text == '/skip')
async def createTask(message):
    print('got in createTask')
    if not stack[message.chat.id]['taskObject']:
        try:
            idObject = int(message.text)
            objectNameGot = db.ex('SELECT object FROM task WHERE id = %s', (idObject,))[0][0]
            stack[message.chat.id]['taskObject'] = objectNameGot
        except ValueError:
            stack[message.chat.id]['taskObject'] = message.text
        print('Task object is', stack[message.chat.id]['taskObject'])
        carList = await getAutoList()
        await bot.send_message(message.chat.id, 'Теперь введите номер(цифру перед названием) автомобиля, на котором была совершена поездка\n' + carList)
    elif not stack[message.chat.id]['taskCar']:
        try:
            idCar = int(message.text)
            if not db.ex('SELECT * FROM auto WHERE id = %s', (idCar,)):
                await bot.send_message(message.chat.id, 'Машины с таким id не найдено в базе, попробуйте еще раз')
            else:
                stack[message.chat.id]['taskCar'] = idCar
                print('Task car is', stack[message.chat.id]['taskCar'])
                employeeList = await getEmployees(coeff = False)
                await bot.send_message(message.chat.id, 'Отлично, теперь введите номер напарника, с которым вы выполняли задачу\nЕсли вы выполняли ее самостоятельно, то отправьте слово /skip\n\n' + employeeList)
        except ValueError:
            await bot.send_message(message.chat.id, 'Число введено некорректно, попробуйте еще раз')
    elif not stack[message.chat.id]['taskBuddy']:
        if message.text == '/skip':
            stack[message.chat.id]['taskBuddy'] = 'flagSkipped'
            await bot.send_message(message.chat.id, 'Супер, теперь введите количество километров, затраченных на поездку')
        else:
            try:
                idBuddy = int(message.text)
                if not db.ex('SELECT * FROM employee WHERE id = %s', (idBuddy,)):
                    await bot.send_message(message.chat.id, 'Сотрудника с таким id не найдено в базе, попробуйте еще раз')
                else:
                    stack[message.chat.id]['taskBuddy'] = idBuddy
                    await bot.send_message(message.chat.id, 'Супер, теперь введите количество километров, затраченных на поездку')
            except ValueError:
                await bot.send_message(message.chat.id, 'Число введено некорректно, попробуйте еще раз')
        print('Task buddy is', stack[message.chat.id]['taskBuddy'])
    elif not stack[message.chat.id]['taskKm']:
        await insertDigit(message, 'taskKm', 'Отлично, теперь введите количество часов, которое заняла поездка', int)
    elif not stack[message.chat.id]['taskTime']:
        await insertDigit(message, 'taskTime', 'Теперь введите сумму, полученную за заказ', int)
    elif not stack[message.chat.id]['taskIncome']:
        await insertDigit(message, 'taskIncome', 'Теперь расходы', float)
    else:
        clearUserStack(message.chat.id)
        await bot.send_message(message.chat.id, 'С отчетом о поездке произошла ошибка :(\nПерейдите в личный кабинет /office и попробуйте еще раз')

async def getAutoList():
    carList = db.ex('SELECT * FROM auto')
    if carList:
        carList = '\n'.join([' '.join([str(obj) for obj in item]) for item in carList])
    else:
        carList = 'Список авто пуст'
    return carList

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

async def getEmployees(coeff):
    employeeList = db.ex(f'SELECT id, name{", coeff" if coeff else ""} FROM employee WHERE deleted IS NOT TRUE')
    if employeeList:
        employeeList = '\n'.join([' '.join([str(obj) for obj in item]) for item in employeeList])
    else:
        employeeList = 'Список сотрудников пуст'
    return employeeList

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

@bot.message_handler(commands=['authuser', 'authowner'])
async def auth(message):
    role = message.text[5:]
    for owner in db.ex("SELECT chatid FROM users WHERE role = 'owner'"):
        await bot.send_message(owner[0], f'Новый запрос на авторизацию пользователя от @{message.chat.username}\nЗапрашиваемая роль: {rolemapping[role]}', reply_markup=mk.createMarkup(1, ['Авторизовать'],[f'auth_{message.chat.username}_{message.chat.id}_{role}_{owner[0]}']))

@bot.message_handler(commands=['office'])
async def messageHandler(message):
    getRole = db.ex('SELECT role FROM users WHERE chatid = %s', (int(message.chat.id),))
    if not getRole:
        await bot.send_message(message.chat.id, 'Такой пользователь не зарегистрирован в системе\nОбратитесь к администратору\n/authuser для авторизации')
    elif getRole[0][0] == 'owner':
        await bot.send_message(message.chat.id, "Личный кабинет администратора", reply_markup=mk.createMarkup(2, ['Автомобили', 'Сотрудники', 'Затраты', 'Доходы'], ['adAuto', 'adEmployee', 'adExpenses', 'adIncome']))
    elif getRole[0][0] == 'user':
        await bot.send_message(message.chat.id, 'Личный кабинет сотрудника', reply_markup=mk.createMarkup(1,['Отчитаться о поездке','Мои доходы'],['userTask','userIncome']))
    else:
        await bot.send_message(message.chat.id, 'Проблемы с ролью пользователя\nОбратитесь к администратору')
    clearUserStack(message.chat.id)


def main():
    asyncio.run(bot.polling())

if __name__ == '__main__':
    main()
