from telebot import TeleBot
import datetime as dt
import json
import requests
import io

import constants
from dbhandler import dbHandler
from markups import markup as mk
baseurl = 'https://cloud-api.yandex.net/v1/disk/'
yandexHeaders = {'Authorization': constants.DISKAPIKEY}
bot = TeleBot(constants.APIKEY, parse_mode=None)
db = dbHandler(constants.DBPARAMS)
stack = {}
rolemapping = {'user': 'пользователь', 'owner': 'владелец'}
month = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
         'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']


def stackFilter(message, term, mustbedigit=False):
    if mustbedigit and not message.text.isdigit:
        return False
    if not stack.get(message.chat.id, False):
        return False
    return stack[message.chat.id].get(term, False)


def clearUserStack(id):
    stack[id] = {}


def periodHandler(calldata, index, keyword, table):
    try:
        period = int(calldata[index:])
    except ValueError:
        return ''
    else:
        return f" {keyword} {table}.time >= NOW() - INTERVAL '{period} day'"


def csvCreator(headers, array):
    rows = '\n'.join([';'.join([str(obj).replace(';', ',')
                     for obj in item]) for item in array])
    return io.StringIO(headers + rows)


def csvLoadSender(idUser, expense, callData):
    if expense:
        period = periodHandler(callData, 12, 'AND', 'task')
        load = db.ex("SELECT date_trunc('minute', expenses.time), COALESCE(task.object, 'Расход без объекта'), COALESCE(employee.name, employee.handle), amount, note FROM expenses LEFT JOIN task ON taskid = task.id JOIN employee ON employeeid = employee.id WHERE confirmed = True" + period)
        headers = 'Время;Объект;Сотрудник;Сумма;Заметка\n'
    else:
        period = periodHandler(callData, 10, 'AND', 'task')
        load = db.ex("SELECT date_trunc('minute', time), task.object, COALESCE(employee.name, employee.handle), income FROM employeetotask JOIN employee ON employeeid = employee.id JOIN task ON taskid = task.id WHERE main = true" + period)
        headers = 'Время;Объект;Сотрудник;Сумма\n'
    if not load:
        bot.send_message(idUser, 'Записей за данный период не найдено')
    else:
        bot.send_document(idUser, csvCreator(
            headers, load), visible_file_name=f'{"Расходы" if expense else "Доходы"}.csv')


def insertDigit(message, direction, note, func):
    try:
        digit = func(message.text.replace(',', '.'))
        stack[message.chat.id][direction] = digit
        if note:
            bot.send_message(message.chat.id, note)
    except ValueError:
        bot.send_message(
            message.chat.id, 'Число введено некорректо, попробуйте еще раз')


def coalesce(array):
    try:
        return int(array[0][0])
    except:
        return 0


def getAutoList():
    carList = db.ex(
        'SELECT id, name, color, licensenum FROM auto WHERE deleted IS NOT True')
    if carList:
        carList = '\n'.join([' '.join([str(obj) for obj in item])
                            for item in carList])
    else:
        carList = 'Список авто пуст'
    return carList


def getEmployees(coeff):
    employeeList = db.ex(
        f'SELECT id, name{", coeff, wage" if coeff else ""} FROM employee WHERE deleted IS NOT TRUE AND name IS NOT NULL ORDER BY id')
    if employeeList:
        employeeList = '\n'.join(
            [' '.join([str(obj) for obj in item]) for item in employeeList])
    else:
        employeeList = 'Список сотрудников пуст'
    unnamedEmployee = db.ex(
        'SELECT id, handle FROM employee WHERE deleted IS NOT TRUE AND name IS NULL')
    if unnamedEmployee:
        unnamedEmployee = '\n'.join(
            [' '.join([str(obj) for obj in item]) for item in unnamedEmployee])
        unnamedEmployee = '\nВ базе также есть несколько сотрудников с неподтвержденным именем:\n' + unnamedEmployee
    else:
        unnamedEmployee = ''
    return employeeList + unnamedEmployee


def uploadPicture(file, message):
    addurl = f"resources/upload?path={constants.DISKFOLDER}{str(dt.datetime.now())[:21].replace(':','-')} {message.chat.first_name}"
    r = requests.get(baseurl+addurl, headers=yandexHeaders)
    if r.status_code != 200:
        return False
    r = json.loads(r.text)
    files = {'file': file}
    r = requests.put(r['href'], headers=yandexHeaders, files=files)
    return r.status_code == 201


@bot.message_handler(content_types=['photo'])
def photoHandler(message):
    getRole = db.ex('SELECT role FROM employee WHERE chatid = %s AND deleted IS NOT True',
                    (int(message.chat.id),))
    if not getRole or (getRole and getRole[0][0] != 'user'):
        return
    file = bot.get_file(message.photo[-1].file_id)
    file = bot.download_file(file.file_path)
    if uploadPicture(file, message):
        bot.send_message(message.chat.id, 'Фото успешно загружено')
    else:
        bot.send_message(
            message.chat.id, 'С загрузкой фотографии произошла ошибка, обратитесь к администратору')


@bot.message_handler(commands=['start'])
def startHandler(message):
    bot.send_message(message.chat.id, 'Добро пожаловать!\nДля авторизации как сотрудник отправьте команду /authuser\nДля авторизации как администатор отправьте команду /authowner\nВашу заявку должен подтвердить администратор')


@bot.message_handler(commands=['office'])
def messageHandler(message):
    getRole = db.ex('SELECT role FROM employee WHERE chatid = %s AND deleted IS NOT True',
                    (int(message.chat.id),))
    if not getRole:
        bot.send_message(
            message.chat.id, 'Такой пользователь не зарегистрирован в системе\nОбратитесь к администратору\n/authuser для авторизации')
    elif getRole[0][0] == 'owner':
        bot.send_message(message.chat.id, "Личный кабинет администратора", reply_markup=mk.createMarkup(2, ['Автомобили', 'Сотрудники', 'Затраты', 'Доходы', 'Сводка', 'Выдать З/П', 'Поездки', 'Зарплата', 'Подтвердить расходы'], [
                         'adAuto', 'adEmployee', 'adExpenses', 'adIncome', 'adPivot', 'adWage', 'adObjects', 'adLoadWage', 'adApproveExpenses']))
    elif getRole[0][0] == 'user':
        bot.send_message(message.chat.id, 'Личный кабинет сотрудника\nДля загрузки фотоотчета просто отправьте фотографию боту', reply_markup=mk.createMarkup(
            1, ['Отчитаться о поездке', 'Мои доходы', 'Учесть расход'], ['userTask', 'userIncome0', 'userAddExpense']))
    else:
        bot.send_message(
            message.chat.id, 'Проблемы с ролью пользователя\nОбратитесь к администратору')
    clearUserStack(message.chat.id)


@bot.message_handler(commands=['authuser', 'authowner'])
def auth(message):
    role = message.text[5:]
    currentRole = db.ex(
        'SELECT role, deleted  FROM employee WHERE chatid = %s', (message.chat.id,))
    if currentRole and (currentRole[0][0] == role or currentRole[0][1]):
        bot.send_message(message.chat.id, 'Вы уже авторизованы')
        return
    for owner in db.ex("SELECT chatid FROM employee WHERE role = 'owner'"):
        bot.send_message(owner[0], f'Новый запрос на авторизацию пользователя от {message.chat.first_name if message.chat.first_name else ""} {message.chat.last_name if message.chat.last_name else ""}\n@{message.chat.username}\nЗапрашиваемая роль: {rolemapping[role]}', reply_markup=mk.createMarkup(
            1, ['Авторизовать'], [f'auth//{message.chat.username if message.chat.username else f"{message.chat.first_name}"}//{message.chat.id}//{role}//{owner[0]}']))
    bot.send_message(
        message.chat.id, 'Запрос на авторизацию успешно отправлен, ожидайте ответа администратора')


@bot.message_handler(func=lambda message: stackFilter(message, 'creatingTask') or message.text == '/skip')
def createTask(message):
    if not stack[message.chat.id]['taskObject']:
        try:
            idObject = int(message.text)
            objectNameGot = db.ex(
                'SELECT object FROM task WHERE id = %s', (idObject,))[0][0]
            stack[message.chat.id]['taskObject'] = objectNameGot
        except ValueError:
            stack[message.chat.id]['taskObject'] = message.text
        carList = getAutoList()
        bot.send_message(
            message.chat.id, 'Теперь введите номер(цифру перед названием) автомобиля, на котором была совершена поездка\n' + carList)
    elif not stack[message.chat.id]['taskCar']:
        try:
            idCar = int(message.text)
            if not db.ex('SELECT * FROM auto WHERE id = %s', (idCar,)):
                bot.send_message(
                    message.chat.id, 'Машины с таким id не найдено в базе, попробуйте еще раз')
            else:
                stack[message.chat.id]['taskCar'] = idCar
                employeeList = getEmployees(coeff=False)
                bot.send_message(
                    message.chat.id, 'Отлично, теперь введите номера напарников, с которым вы выполняли задачу\nЕсли вы выполняли ее самостоятельно, то отправьте слово /skip\n\n' + employeeList + f'\n\nомера напарников нужно вводить одним сообщением через пробел:\n2 4 16 17 9')
        except ValueError:
            bot.send_message(
                message.chat.id, 'Число введено некорректно, попробуйте еще раз')
    elif not stack[message.chat.id]['taskBuddy']:
        if message.text == '/skip':
            stack[message.chat.id]['taskBuddy'] = 'flagSkipped'
            bot.send_message(
                message.chat.id, 'Супер, теперь введите количество километров, затраченных на поездку')
        else:
            try:
                data = []
                for ind in message.text.split():
                    ind = int(ind)
                    chatid = db.ex('SELECT chatid FROM employee WHERE id = %s', (ind,))
                    if not chatid:
                        bot.send_message(
                            message.chat.id, f'Сотрудник с id {ind} не найден в базе, отправьте сообщение еще раз')
                        return
                    elif int(chatid[0][0]) == message.chat.id:
                        bot.send_message(
                            message.chat.id, f'Вы не можете указать в качестве напарника самого себя!')
                        return
                    else:
                        data.append(ind)
            except ValueError:
                bot.send_message(
                    message.chat.id, f'Одно из чисел ({ind}) введено некорректно, попробуйте еще раз')
                return
            stack[message.chat.id]['taskBuddy'] = data
            print(data)
            bot.send_message(
                message.chat.id, 'Супер, теперь введите количество километров, затраченных на поездку')
    elif not stack[message.chat.id]['taskKm']:
        insertDigit(message, 'taskKm',
                    'Отлично, теперь введите количество часов, которое заняла поездка', int)
    elif not stack[message.chat.id]['taskTime']:
        insertDigit(message, 'taskTime',
                    'Теперь введите сумму, полученную за заказ', int)
    elif not stack[message.chat.id]['taskIncome']:
        insertDigit(message, 'taskIncome', 'Теперь нужно отчитаться о связанных с поездкой расходах\nКаждую статью расходов нужно описать отдельным сообщением в следующей форме: \n\n1500 на бензин\n300 на мобильную связь\n\nКогда вы укажете все расходы(или если они отсутствуют), отправьте команду /skip', float)
    elif not stack[message.chat.id]['taskExpensesFinished']:
        if message.text == '/skip':
            stack[message.chat.id]['taskExpensesFinished'] = True
            idTask = db.ex('INSERT INTO task(object, car, kmspent, hoursspent, income, time) VALUES (%s, %s, %s, %s, %s, NOW()) RETURNING *',
                           (stack[message.chat.id]['taskObject'], stack[message.chat.id]['taskCar'], stack[message.chat.id]['taskKm'], stack[message.chat.id]['taskTime'], stack[message.chat.id]['taskIncome']))[0][0]
            idTaskMaker = db.ex(
                'SELECT id FROM employee WHERE chatid = %s', (message.chat.id,))[0][0]
            db.ex('INSERT INTO employeetotask(employeeid, taskid, main) VALUES(%s, %s, True)',
                  (idTaskMaker, idTask))
            if stack[message.chat.id]['taskBuddy'] != 'flagSkipped':
                for id in stack[message.chat.id]['taskBuddy']:
                    db.ex('INSERT INTO employeetotask(employeeid, taskid, main) VALUES (%s, %s, False) ON CONFLICT DO NOTHING',
                      (id, idTask))
            if stack[message.chat.id]['taskExpenses']:
                for expense in stack[message.chat.id]['taskExpenses']:
                    db.ex('INSERT INTO expenses(taskid, employeeid, amount, note) VALUES (%s, %s, %s, %s)',
                          (idTask, idTaskMaker, expense[0], expense[1]))
            bot.send_message(
                message.chat.id, 'Готово! Отчет успешно внесен в базу\n/office для перехода в личный кабинет')
            clearUserStack(message.chat.id)
        else:
            expense = message.text.split()
            try:
                value = int(expense[0])
            except ValueError:
                bot.send_message(
                    message.chat.id, 'Сумма расхода введена некорректно\nВерный формат: 1000 на бензин')
            else:
                if expense and len(expense) > 1:
                    stack[message.chat.id]['taskExpenses'].append(
                        (value, ' '.join(expense[1:])))
    else:
        clearUserStack(message.chat.id)
        bot.send_message(
            message.chat.id, 'С отчетом о поездке произошла ошибка :(\nПерейдите в личный кабинет /office и попробуйте еще раз')


@bot.message_handler(func=lambda message: stackFilter(message, 'addingAuto'))
def addingAuto(message):
    if not stack[message.chat.id]['addingAutoName']:
        stack[message.chat.id]['addingAutoName'] = message.text
        bot.send_message(message.chat.id, 'Теперь введите цвет машины')
    elif not stack[message.chat.id]['addingAutoColor']:
        stack[message.chat.id]['addingAutoColor'] = message.text
        bot.send_message(
            message.chat.id, 'Теперь введите номерной знак машины')
    else:
        db.ex('INSERT INTO auto(name, color, licensenum) VALUES (%s, %s, %s)', param=(
            stack[message.chat.id]['addingAutoName'], stack[message.chat.id]['addingAutoColor'], message.text))
        bot.send_message(message.chat.id, 'Готово! Машина добавлена в базу', reply_markup=mk.createMarkup(
            2, ['Добавить еще', 'Закончить'], ['adAutoAdd', 'endAutoAdd']))


@bot.message_handler(func=lambda message: stackFilter(message, 'deletingAuto', mustbedigit=True))
def autoDeleter(message):
    db.ex('UPDATE auto SET deleted = True WHERE id = %s',
          param=(int(message.text),))
    bot.send_message(message.chat.id, f'Машина {message.text} удалена из базы', reply_markup=mk.createMarkup(
        2, ['Удалить еще', 'Закончить'], ['adAutoDelete', 'endAutoDelete']))


@bot.message_handler(func=lambda message: stackFilter(message, 'updateEmployee'))
def addingEmployee(message):
    if not stack[message.chat.id]['updateEmployeeId']:
        insertDigit(message, 'updateEmployeeId',
                    'Теперь введите имя для сотрудника', int)
    elif not stack[message.chat.id]['updateEmployeeName']:
        stack[message.chat.id]['updateEmployeeName'] = message.text
        bot.send_message(
            message.chat.id, 'Теперь введите коэффициент зарплаты для сотрудника (введите 1, чтобы оставить сотрудника без коэффициента)')
    elif not stack[message.chat.id]['updateEmployeeCoeff']:
        insertDigit(message, 'updateEmployeeCoeff',
                    'Отлично, теперь введите часовую ставку сотрудника', float)
    elif not stack[message.chat.id]['updateEmployeeWage']:
        insertDigit(message, 'updateEmployeeWage', None, int)
        db.ex('UPDATE employee SET name = %s, coeff = %s, wage = %s WHERE id = %s', (stack[message.chat.id]['updateEmployeeName'], stack[
              message.chat.id]['updateEmployeeCoeff'], stack[message.chat.id]['updateEmployeeWage'], stack[message.chat.id]['updateEmployeeId']))
        bot.send_message(message.chat.id, 'Готово! Информация о сотруднике отредактирована', reply_markup=mk.createMarkup(
            2, ['Обновить еще', 'Закончить'], ['adEmployeeUpdate', 'endEmployeeUpdate']))


@bot.message_handler(func=lambda message: stackFilter(message, 'deletingEmployee', mustbedigit=True))
def deletingEmployee(message):
    db.ex('UPDATE employee SET deleted = True WHERE id = %s', param=(message.text,))
    bot.send_message(message.chat.id, f'Сотрудник {message.text} удален из базы', reply_markup=mk.createMarkup(
        2, ['Удалить еще', 'Закончить'], ['adEmployeeDelete', 'endEmployeeDelete']))

@bot.message_handler(func=lambda message: stackFilter(message, 'userAddExpense'))
def addingExpense(message):
    try:
        data = message.text.split()
        amount = int(data[0])
        caption = ' '.join(data[1:])
        if not caption:
            raise IndexError
        db.ex('INSERT INTO expenses(employeeid, amount, note) VALUES ((SELECT id FROM employee WHERE chatid = %s), %s, %s)', (message.chat.id, amount, caption))
    except ValueError:
        bot.send_message(message.chat.id, 'Сумма расхода введена в неверном формате, попробуйте еще раз\nШаблон отчета о расходах: \n1500 на бензин\n300 на мобильную связь')    
    except IndexError:
        bot.send_message(message.chat.id, 'Назначение расхода введено неверно, попробуйте еще раз\nШаблон отчета о расходах: \n1500 на бензин\n300 на мобильную связь')
    else:
        stack[message.chat.id]['userAddExpense'] = False
        bot.send_message(message.chat.id, 'Расход успешно учтен', reply_markup=mk.createMarkup(1, ['Добавить еще','Закончить'], ['userAddExpense','userAddExpenseEnd']))


@bot.callback_query_handler(func=lambda call: True)
def callbackQuery(call):
    print('got a callback', call.data, str(dt.datetime.now()))
    clearUserStack(call.from_user.id)
    if call.data.startswith('auth'):
        data = call.data.split('//')
        db.ex('INSERT INTO employee(handle, chatid, role) VALUES (%s, %s, %s) ON CONFLICT (chatid) DO UPDATE SET role = %s, deleted = NULL WHERE employee.chatid = %s',
              (data[1], int(data[2]), data[3], data[3], int(data[2])))
        bot.send_message(
            data[2], f'Ваши привилегии обновлены\nНовая роль: {rolemapping[data[3]]}\n/office для перехода в личный кабинет')
        bot.edit_message_text(
            'Роль успешно обновлена', call.from_user.id, call.message.id, reply_markup=None)
    elif call.data == "adAuto":
        autoList = getAutoList()
        bot.send_message(call.from_user.id, 'Список авто:\n' + autoList,
                         reply_markup=mk.createMarkup(2, ['Добавить', 'Удалить'], ['adAutoAdd', 'adAutoDelete']))
    elif call.data == "adAutoAdd":
        stack[call.from_user.id]['addingAuto'] = True
        stack[call.from_user.id]['addingAutoName'] = None
        stack[call.from_user.id]['addingAutoColor'] = None
        bot.send_message(
            call.from_user.id, 'Добавляем автомобиль в базу\nВведите название автомобиля')
    elif call.data == "endAutoAdd":
        stack[call.from_user.id]['addingAuto'] = False
        bot.send_message(
            call.from_user.id, 'Добавление закончено\n/office для входа в личный кабинет')
    elif call.data == "adAutoDelete":
        bot.send_message(
            call.from_user.id, 'Введите номер автомобиля, который желаете удалить из базы')
        stack[call.from_user.id]['deletingAuto'] = True
    elif call.data == "endAutoDelete":
        stack[call.from_user.id]['deletingAuto'] = False
        bot.send_message(
            call.from_user.id, 'Удаление автомобилей закончено\n/office для входа в личный кабинет')
    elif call.data == "adEmployee":
        employeeList = getEmployees(coeff=True)
        bot.send_message(call.from_user.id, 'Список сотрудников:\n' + employeeList, reply_markup=mk.createMarkup(
            1, ['Обновить информацию', 'Удалить'], ['adEmployeeUpdate', 'adEmployeeDelete']))
    elif call.data == "adEmployeeUpdate":
        bot.send_message(
            call.from_user.id, 'Введите номер сотрудника, информацию о котором собираетесь редактировать')
        stack[call.from_user.id]['updateEmployee'] = True
        stack[call.from_user.id]['updateEmployeeId'] = None
        stack[call.from_user.id]['updateEmployeeName'] = None
        stack[call.from_user.id]['updateEmployeeCoeff'] = None
        stack[call.from_user.id]['updateEmployeeWage'] = None
    elif call.data == "endEmployeeUpdate":
        stack[call.from_user.id]['addingEmployee'] = False
        bot.send_message(
            call.from_user.id, 'Обновление закончено\n/office для входа в личный кабинет')
    elif call.data == "adEmployeeDelete":
        bot.send_message(
            call.from_user.id, 'Введите номер сотрудника, которого желаете удалить из базы')
        stack[call.from_user.id]['deletingEmployee'] = True
    elif call.data == "endEmployeeDelete":
        stack[call.from_user.id]['deletingEmployee'] = False
        bot.send_message(
            call.from_user.id, 'Удаление сотрудников закончено\n/office для входа в личный кабинет')
    elif call.data == "adExpenses":
        bot.send_message(call.from_user.id, 'Выберите период выгрузки расходов', reply_markup=mk.createMarkup(
            2, ['24 часа', 'Неделя', 'Месяц', 'Все время'], ['loadExpenses1', 'loadExpenses7', 'loadExpenses30', 'loadExpensesAll']))
    elif call.data.startswith('loadExpenses'):
        csvLoadSender(call.from_user.id, True, call.data)
    elif call.data == "adIncome":
        bot.send_message(call.from_user.id, 'Выберите период выгрузки доходов', reply_markup=mk.createMarkup(
            2, ['24 часа', 'Неделя', 'Месяц', 'Все время'], ['loadIncome1', 'loadIncome7', 'loadIncome30', 'loadIncomeAll']))
    elif call.data.startswith('loadIncome'):
        csvLoadSender(call.from_user.id, False, call.data)
    elif call.data == 'adPivot':
        bot.send_message(call.from_user.id, 'Выберите период выгрузки', reply_markup=mk.createMarkup(
            2, ['24 часа', 'Неделя', 'Месяц', 'Все время'], ['loadPivot1', 'loadPivot7', 'loadPivot30', 'loadPivotAll']))
    elif call.data.startswith('loadPivot'):
        period = periodHandler(call.data, 9, 'WHERE', 'task')
        income = db.ex('SELECT sum(income) FROM task' + period)
        income = coalesce(income)
        period = periodHandler(call.data, 9, 'AND', 'expenses')
        expenses = db.ex(
            'SELECT sum(amount) FROM expenses WHERE confirmed = True' + period)
        expenses = coalesce(expenses)
        period = periodHandler(call.data, 9, 'WHERE', 'payments')
        wage = db.ex(
            'SELECT sum(payments.amount) FROM payments JOIN employeetotask ON employeetotaskid = employeetotask.id JOIN task ON taskid = task.id' + period)
        wage = coalesce(wage)
        profit = income - expenses - wage
        if not period:
            pivot = 'Сводка за все время:\n'
        else:
            days = period.split("'")[1].split()[0]
            pivot = f'Сводка за {days} {"день" if int(days) == 1 else "дней"}\n'
        pivot = pivot + \
            f"Доходы: {income}\nРасходы: {expenses}\nРасходы на З/П: {wage}\nПрибыль: {profit}"
        bot.send_message(call.from_user.id, pivot)
    elif call.data == 'adWage':
        bot.send_message(call.from_user.id, 'Администратору предстоит подтвердить совершенные поездки и начислить за них заработную плату сотрудникам\nЗарплата подтверждается только для сотрудников с установленой часовой ставкой',
                         reply_markup=mk.createMarkup(1, ['Продолжить?'], ['adWageStart']))
    elif call.data.startswith('adWageStart'):
        if call.data != 'adWageStart':
            data = call.data.split('//')
            if call.data[11:].startswith('Apply'):
                db.ex(
                    'UPDATE employeetotask SET paid = true WHERE id = %s', (data[1],))
                db.ex(
                    'INSERT INTO payments(employeetotaskid, amount, time) VALUES (%s, %s, NOW())', (data[1], data[2]))
            else:
                db.ex(
                    'UPDATE employeetotask SET paid = false WHERE id = %s', (data[1],))
        load = db.ex('SELECT COALESCE(name, handle), object, hoursspent, hoursspent * wage * coeff, employeetotask.id AS sum FROM employeetotask JOIN employee ON employeeid = employee.id JOIN task ON taskid = task.id WHERE paid IS NULL AND wage IS NOT NULL LIMIT 1;')
        if load:
            employeeToTaskId = load[0][4]
            amount = load[0][3]
            load = f'Выплата для сотрудника {load[0][0]} за поездку на объект {load[0][1]}\nЗатрачено часов: {load[0][2]}\nВыплата: {int(load[0][3])}'
            bot.send_message(call.from_user.id, load, reply_markup=mk.createMarkup(1, ['Подтвердить выплату', 'Отклонить выплату'], [
                             f'adWageStartApply//{employeeToTaskId}//{amount}', f'adWageStartReject//{employeeToTaskId}']))
        else:
            bot.send_message(call.from_user.id,
                             'Не найдено неоплаченных поездок\n/office')
    elif call.data == "userTask":
        stack[call.from_user.id]['creatingTask'] = True
        stack[call.from_user.id]['taskObject'] = None
        stack[call.from_user.id]['taskCar'] = None
        stack[call.from_user.id]['taskBuddy'] = []
        stack[call.from_user.id]['taskKm'] = None
        stack[call.from_user.id]['taskTime'] = None
        stack[call.from_user.id]['taskIncome'] = None
        stack[call.from_user.id]['taskExpenses'] = []
        stack[call.from_user.id]['taskExpensesFinished'] = False
        lastObject = db.ex(
            'SELECT DISTINCT ON(object) id, object FROM task ORDER BY object, time DESC LIMIT 10;')
        if not lastObject:
            queryText = 'Заполняем задачу\nДля начала введите название объекта:'
        else:
            lastObject = '\n'.join(
                [' '.join([str(obj) for obj in item]) for item in lastObject])
            queryText = 'Заполняем задачу\nВведите название нового объекта или пришлите номер одного из представленных:\n\n' + lastObject
        bot.send_message(call.from_user.id, queryText)
    elif call.data.startswith('userIncome'):
        period = int(call.data[10:])
        load = db.ex(
            f"SELECT sum(amount) FROM payments JOIN employeetotask ON employeetotaskid = employeetotask.id WHERE employeeid = (SELECT id FROM employee WHERE chatid = %s) AND date_trunc('month', NOW()) - INTERVAL '{period} month'  = date_trunc('month', time);", (call.from_user.id,))
        if period == 0:
            markup = mk.createMarkup(
                1, ['\U00002B05'], [f'userIncome{period + 1}'])
        else:
            markup = mk.createMarkup(2, ['\U00002B05', '\U000027A1'], [
                                     f'userIncome{period + 1}', f'userIncome{period - 1}'])
        if not load[0][0]:
            load = 'Доходов за данный период не найдено'
        else:
            load = f'{int(load[0][0])} руб'
        monthNum = (dt.datetime.today() - dt.timedelta(days=period*30)).month
        bot.edit_message_text(
            f'Доходы за {month[monthNum - 1]}\n{load}', call.from_user.id, call.message.id, reply_markup=markup)
    elif call.data == 'userAddExpense':
        bot.send_message(
            call.from_user.id, 'Каждую статью расходов нужно описать отдельным сообщением в следующей форме:\nсумма расхода+пробел+назначение расхода \n\n1500 на бензин\n300 на мобильную связь')
        stack[call.from_user.id]['userAddExpense'] = True
    elif call.data == "userAddExpenseEnd":
        stack[call.from_user.id]['userAddExpense'] = False
        bot.send_message(
            call.from_user.id, 'Внесение расходов завершено\n/office для входа в личный кабинет')
    elif call.data == 'adObjects':
        load = db.ex("SELECT task.id, date_trunc('minutes', time), object, (SELECT name FROM employeetotask JOIN employee ON employeeid = employee.id WHERE task.id = taskid AND main = true), (SELECT name FROM employeetotask JOIN employee ON employeeid = employee.id WHERE task.id = taskid AND main = false), auto.name, kmspent, hoursspent, income, (SELECT sum(amount) FROM expenses WHERE taskid = task.id AND confirmed = True) FROM task JOIN auto ON task.car = auto.id;")
        if not load:
            bot.send_message(call.from_user.id, 'Поездок не найдено')
        else:
            bot.send_document(call.from_user.id, csvCreator(
                'ID;Дата;Объект;Сотрудник;Напарник;Авто;Километраж;Длительность;Доход;Расход\n', load), visible_file_name='Поездки.csv')
    elif call.data.startswith('adLoadWage'):
        if call.data == 'adLoadWage':
            bot.send_message(call.from_user.id, 'Выберите период выгрузки транзакций З\П', reply_markup=mk.createMarkup(
                2, ['24 часа', 'Неделя', 'Месяц', 'Все время'], ['adLoadWage1', 'adLoadWage7', 'adLoadWage30', 'adLoadWageAll']))
        else:
            period = periodHandler(call.data, 10, 'WHERE', 'payments')
            load = db.ex(
                f'SELECT COALESCE(employee.name, employee.handle), sum(amount) FROM payments JOIN employeetotask ON employeetotask.id = employeetotaskid JOIN employee ON employeeid = employee.id {period} GROUP BY employee.handle')
            if not load:
                bot.send_message(call.from_user.id,
                                 'Выплат за данный период не найдено')
            else:
                bot.send_document(call.from_user.id, csvCreator(
                    'Сотрудник,Выплата\n', load), visible_file_name='Зарплаты.csv')
    elif call.data.startswith('adApproveExpenses'):
        if call.data != 'adApproveExpenses':
            db.ex('UPDATE expenses SET confirmed = %s WHERE id = %s',
                  (call.data[17:].startswith('Acc'), call.data[20:]))
        load = db.ex("SELECT expenses.id, COALESCE(task.object, 'Расход без объекта'), COALESCE(employee.name, employee.handle), amount, note, date_trunc('minute', expenses.time) FROM expenses LEFT JOIN task ON task.id = taskid JOIN employee ON employeeid = employee.id WHERE confirmed IS NULL LIMIT 1; ")
        if not load:
            bot.send_message(
                call.from_user.id, 'Неподтвержденных расходов не найдено\n/office для перехода в личный кабинет')
        else:
            bot.send_message(call.from_user.id, f'Поездка: {load[0][1]}\nСотрудник: {load[0][2]}\nСумма: {load[0][3]}\nЦель расхода: {load[0][4]}\n{load[0][5]}', reply_markup=mk.createMarkup(
                1, ['Подтвердить', 'Отклонить'], [f'adApproveExpensesAcc{load[0][0]}', f'adApproveExpensesRej{load[0][0]}']))
  

def main():
    print('polling!')
    bot.infinity_polling()


if __name__ == '__main__':
    main()
