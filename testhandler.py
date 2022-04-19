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
rolemapping = {'user':'пользователь','owner':'владелец'}

def stackFilter(message, term, mustbedigit = False):
    if mustbedigit and not message.text.isdigit:
        return False
    if not stack.get(message.chat.id, False):
        return False
    return stack[message.chat.id].get(term, False)

def clearUserStack(id):
    stack[id] = {}

@bot.message_handler(commands=['office'])
async def messageHandler(message):
    getRole = db.ex('SELECT role FROM employee WHERE chatid = %s', (int(message.chat.id),))
    if not getRole:
        await bot.send_message(message.chat.id, 'Такой пользователь не зарегистрирован в системе\nОбратитесь к администратору\n/authuser для авторизации')
    elif getRole[0][0] == 'owner':
        await bot.send_message(message.chat.id, "Личный кабинет администратора", reply_markup=mk.createMarkup(2, ['Автомобили', 'Сотрудники', 'Затраты', 'Доходы', 'Сводка', 'Выдать З/П'], ['adAuto', 'adEmployee', 'adExpenses', 'adIncome', 'adPivot', 'adWage']))
    elif getRole[0][0] == 'user':
        await bot.send_message(message.chat.id, 'Личный кабинет сотрудника', reply_markup=mk.createMarkup(1,['Отчитаться о поездке','Мои доходы'],['userTask','userIncome']))
    else:
        await bot.send_message(message.chat.id, 'Проблемы с ролью пользователя\nОбратитесь к администратору')
    clearUserStack(message.chat.id)

async def csvLoadSender(idUser, expense, callData):
    try:
        period = int(callData[12:])
    except ValueError:
        period = ''
    else:
        period = f" WHERE time >= NOW()::date - INTEGER '{period}'"
    if expense:
        load = db.ex("SELECT date_trunc('minute', time), task.object, COALESCE(employee.name, employee.handle), amount, note FROM expenses JOIN task ON taskid = task.id JOIN employee ON employeeid = employee.id" + period)
        headers = 'Время,Объект,Сотрудник,Сумма,Заметка\n'
    else:
        load = db.ex("SELECT date_trunc('minute', time), task.object, COALESCE(employee.name, employee.handle), income FROM employeetotask JOIN employee ON employeeid = employee.id JOIN task ON taskid = task.id WHERE main = true" + period)
        headers = 'Время,Объект,Сотрудник,Сумма\n'
    if not load:
        await bot.send_message(idUser, 'Записей за данный период не найдено')
    else:
        load = '\n'.join([','.join([str(obj) for obj in item]) for item in load])
        fh = io.StringIO(headers + load)
        await bot.send_document(idUser, fh, visible_file_name = f'{"Expenses" if expense else "Income"}.csv')

async def insertDigit(message, direction, note, func):
    try:
        digit = func(message.text.replace(',' , '.'))
        stack[message.chat.id][direction] = digit
        print(f'{direction} is {digit}')
        if note:
            await bot.send_message(message.chat.id, note)
    except ValueError:
        await bot.send_message(message.chat.id, 'Число введено некорректо, попробуйте еще раз')

@bot.callback_query_handler(func=lambda call: True)
async def callbackQuery(call):
    clearUserStack(call.from_user.id)
    if call.data.startswith('auth'):
        data = call.data.split('//')
        db.ex('INSERT INTO employee(handle, chatid, role) VALUES (%s, %s, %s) ON CONFLICT (chatid) DO UPDATE SET role = %s WHERE employee.chatid = %s', (data[1], int(data[2]), data[3], data[3], int(data[2])))
        await bot.send_message(data[2], f'Ваши привилегии обновлены\nНовая роль: {rolemapping[data[3]]}\n/office для перехода в личный кабинет')
        await bot.send_message(data[-1], 'Роль успешно обновлена')
    elif call.data == "adAuto":
        autoList = await getAutoList()
        await bot.send_message(call.from_user.id, 'Список авто:\n' + autoList, reply_markup=mk.createMarkup(2, ['Добавить', 'Удалить'], ['adAutoAdd', 'adAutoDelete']))
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
        employeeList = await getEmployees(coeff = True)
        await bot.send_message(call.from_user.id, 'Список сотрудников:\n' + employeeList, reply_markup=mk.createMarkup(1, ['Обновить информацию', 'Удалить'], ['adEmployeeUpdate', 'adEmployeeDelete']))
    elif call.data == "adEmployeeUpdate":
        await bot.send_message(call.from_user.id, 'Сотрудник есть в системе, однако ему нужно назначить имя, зарплату и коэффициент\nВведите номер сотрудника, информацию о котором собираетесь редактировать')
        stack[call.from_user.id]['updateEmployee'] = True
        stack[call.from_user.id]['updateEmployeeId'] = None
        stack[call.from_user.id]['updateEmployeeName'] = None
        stack[call.from_user.id]['updateEmployeeCoeff'] = None
        stack[call.from_user.id]['updateEmployeeWage'] = None
    elif call.data == "endEmployeeUpdate":
        stack[call.from_user.id]['addingEmployee'] = False
        await bot.send_message(call.from_user.id, 'Обновление закончено\n/office для входа в личный кабинет')
    elif call.data == "adEmployeeDelete":
        await bot.send_message(call.from_user.id, 'Введите номер сотрудника, которого желаете удалить из базы')
        stack[call.from_user.id]['deletingEmployee'] = True
    elif call.data == "endEmployeeDelete":
        stack[call.from_user.id]['deletingEmployee'] = False
        await bot.send_message(call.from_user.id, 'Удаление сотрудников закончено\n/office для входа в личный кабинет')
    elif call.data == "adExpenses":
        await bot.send_message(call.from_user.id, 'Выберите период выгрузки расходов', reply_markup=mk.createMarkup(2, ['24 часа', 'Неделя', 'Месяц', 'Все время'], ['loadExpenses1', 'loadExpenses7', 'loadExpenses30', 'loadExpensesAll']))
    elif call.data.startswith('loadExpenses'):
        await csvLoadSender(call.from_user.id, True, call.data)
    elif call.data == "adIncome":
        await bot.send_message(call.from_user.id, 'Выберите период выгрузки доходов', reply_markup=mk.createMarkup(2, ['24 часа', 'Неделя', 'Месяц', 'Все время'], ['loadIncome1', 'loadIncome7', 'loadIncome30', 'loadIncomeAll']))
    elif call.data.startswith('loadIncome'):
        await csvLoadSender(call.from_user.id, False, call.data)
    #сводка по расходам и доходам
    #elif call.data == 'adPivot':
    #    await bot.send_message(call.from_user.id, 'Выберите период выгрузки расходов', reply_markup=mk.createMarkup(2, ['24 часа', 'Неделя', 'Месяц', 'Все время'], ['loadPivot1', 'loadPivot7', 'loadPivot30', 'loadPivotAll']))
    elif call.data == 'adWage':
        await bot.send_message(call.from_user.id, 'Администратору предстоит подтвердить все совершенные поездки и начислить за них заработную плату сотрдуникам', reply_markup=mk.createMarkup(1, ['Продолжить?'],['adWageStart']))
    elif call.data.startswith('adWageStart'):
        if call.data != 'adWageStart':
            pass
            #insert
        print(db.ex('SELECT * FROM employeetotask JOIN employee ON employeeid = employee.id JOIN task ON taskid = task.id WHERE paid IS NOT true'))
        #SELECT name, object, hoursspent, hoursspent * wage * coeff AS sum FROM employeetotask JOIN employee ON employeeid = employee.id JOIN task ON taskid = task.id WHERE paid IS NOT true;
    elif call.data == "userTask":
        stack[call.from_user.id]['creatingTask'] = True
        stack[call.from_user.id]['taskObject'] = None
        stack[call.from_user.id]['taskCar'] = None
        stack[call.from_user.id]['taskBuddy'] = None
        stack[call.from_user.id]['taskKm'] = None
        stack[call.from_user.id]['taskTime'] = None
        stack[call.from_user.id]['taskIncome'] = None
        stack[call.from_user.id]['taskExpenses'] = []
        stack[call.from_user.id]['taskExpensesFinished'] = False
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
        await insertDigit(message, 'taskIncome', 'Теперь нужно отчитаться о связанных с поездкой расходах\nКаждую статью расходов нужно описать отдельным сообщением в следующей форме: \n\n1500 на бензин\n300 на мобильную связь\n\nКогда вы укажете все расходы(или если они отсутствуют), отправьте команду /skip', float)
    elif not stack[message.chat.id]['taskExpensesFinished']:
        if message.text == '/skip':
            stack[message.chat.id]['taskExpensesFinished'] = True
            idTask = db.ex('INSERT INTO task(object, car, kmspent, hoursspent, income, time) VALUES (%s, %s, %s, %s, %s, NOW()) RETURNING *', (stack[message.chat.id]['taskObject'], stack[message.chat.id]['taskCar'], stack[message.chat.id]['taskKm'], stack[message.chat.id]['taskTime'], stack[message.chat.id]['taskIncome']))[0][0]
            idTaskMaker = db.ex('SELECT id FROM employee WHERE chatid = %s', (message.chat.id,))[0][0]
            db.ex('INSERT INTO employeetotask(employeeid, taskid, main) VALUES(%s, %s, True)', (idTaskMaker, idTask))
            if stack[message.chat.id]['taskBuddy']:
                db.ex('INSERT INTO employeetotask(employeeid, taskid, main) VALUES (%s, %s, False) ON CONFLICT DO NOTHING', (stack[message.chat.id]['taskBuddy'], idTask))
            if stack[message.chat.id]['taskExpenses']:
                for expense in stack[message.chat.id]['taskExpenses']:
                    db.ex('INSERT INTO expenses(taskid, employeeid, amount, note) VALUES (%s, %s, %s, %s)', (idTask, idTaskMaker, expense[0], expense[1]))
            await bot.send_message(message.chat.id, 'Готово! Отчет успешно внесен в базу\n/office для перехода в личный кабинет')
            clearUserStack(message.chat.id)
        else:
            expense = message.text.split()
            try:
                value = int(expense[0])
            except ValueError:
                await bot.send_message(message.chat.id, 'Сумма расхода введена некорректно\nВерный формат: 1000 на бензин')
            else:
                if expense and len(expense) > 1:
                    stack[message.chat.id]['taskExpenses'].append((value, ' '.join(expense[1:])))
                    print(stack[message.chat.id]['taskExpenses'])
    else:
        await clearUserStack(message.chat.id)
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
    employeeList = db.ex(f'SELECT id, name{", coeff, wage" if coeff else ""} FROM employee WHERE deleted IS NOT TRUE AND name IS NOT NULL')
    if employeeList:
        employeeList = '\n'.join([' '.join([str(obj) for obj in item]) for item in employeeList])
    else:
        employeeList = 'Список сотрудников пуст'
    unnamedEmployee = db.ex('SELECT id, handle FROM employee WHERE deleted IS NOT TRUE AND name IS NULL')
    if unnamedEmployee:
        unnamedEmployee = '\n'.join([' '.join([str(obj) for obj in item]) for item in unnamedEmployee])
        unnamedEmployee = '\nВ базе также есть несколько сотрудников с неподтвержденным именем:\n' + unnamedEmployee
    else:
        unnamedEmployee = ''
    return employeeList + unnamedEmployee

@bot.message_handler(func=lambda message: stackFilter(message, 'updateEmployee'))
async def addingEmployee(message):
    if not stack[message.chat.id]['updateEmployeeId']:
        await insertDigit(message, 'updateEmployeeId', 'Теперь введите имя для сотрудника', int)
    elif not stack[message.chat.id]['updateEmployeeName']:
        stack[message.chat.id]['updateEmployeeName'] = message.text
        await bot.send_message(message.chat.id, 'Теперь введите коэффициент зарплаты для сотрудника (введите 1, чтобы оставить сотрудника без коэффициента)')
    elif not stack[message.chat.id]['updateEmployeeCoeff']:
        await insertDigit(message, 'updateEmployeeCoeff', 'Отлично, теперь введите часовую ставку сотрудника', float)
    elif not stack[message.chat.id]['updateEmployeeWage']:
        await insertDigit(message, 'updateEmployeeWage', None, int)
        db.ex('UPDATE employee SET name = %s, coeff = %s, wage = %s WHERE id = %s', (stack[message.chat.id]['updateEmployeeName'], stack[message.chat.id]['updateEmployeeCoeff'], stack[message.chat.id]['updateEmployeeWage'], stack[message.chat.id]['updateEmployeeId']))
        await bot.send_message(message.chat.id, 'Готово! Информация о сотруднике отредактирована', reply_markup=mk.createMarkup(2, ['Обновить еще', 'Закончить'], ['adEmployeeUpdate', 'endEmployeeUpdate']))

@bot.message_handler(func=lambda message: stackFilter(message, 'deletingEmployee', mustbedigit = True))
async def deletingEmployee(message):
    db.ex('UPDATE employee SET deleted = True WHERE id = %s', param=(message.text,))
    await bot.send_message(message.chat.id, f'Сотрудник {message.text} удален из базы', reply_markup=mk.createMarkup(2, ['Удалить еще', 'Закончить'], ['adEmployeeDelete', 'endEmployeeDelete']))

@bot.message_handler(commands=['dbtest'])
async def testHandler(message):
    await bot.send_message(message.chat.id, db.ex('SELECT * FROM test;'))

@bot.message_handler(commands=['authuser', 'authowner'])
async def auth(message):
    role = message.text[5:]
    for owner in db.ex("SELECT chatid FROM employee WHERE role = 'owner'"):
        await bot.send_message(owner[0], f'Новый запрос на авторизацию пользователя от @{message.chat.username}\nЗапрашиваемая роль: {rolemapping[role]}', reply_markup=mk.createMarkup(1, ['Авторизовать'],[f'auth//{message.chat.username}//{message.chat.id}//{role}//{owner[0]}']))

def main():
    asyncio.run(bot.polling())

if __name__ == '__main__':
    main()
