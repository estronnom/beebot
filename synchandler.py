from telebot import TeleBot
import datetime as dt
import json
import requests
import logging
import io
import secrets

import constants
from dbhandler import dbHandler
from markups import markup as mk

baseurl = 'https://cloud-api.yandex.net/v1/disk/'
yandex_headers = {'Authorization': constants.DISKAPIKEY}
bot = TeleBot(constants.APIKEY, parse_mode=None)
db = dbHandler(constants.DBPARAMS)
logging.basicConfig(filename='beebot.log',
                    encoding='utf-8',
                    level=logging.INFO,
                    format='%(levelname)s:%(asctime)s %(message)s')
stack = {}
rolemapping = {'user': 'пользователь', 'owner': 'владелец'}
month = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
         'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']


def stack_filter(message, term, mustbedigit=False):
    if mustbedigit and not message.text.isdigit:
        return False
    if not stack.get(message.chat.id, False):
        return False
    return stack[message.chat.id].get(term, False)


def clear_user_stack(user_id):
    stack[user_id] = {}


def period_handler(calldata, index, keyword, table):
    try:
        period = int(calldata[index:])
    except ValueError:
        return ''
    else:
        return f" {keyword} {table}.time >= NOW() - INTERVAL '{period} day'"


def csv_creator(headers, array):
    rows = '\n'.join([';'.join([str(obj).replace(';', ',')
                                for obj in item]) for item in array])
    return headers + rows


def csv_load_sender(id_user, expense, call_data):
    if expense:
        period = period_handler(call_data, 12, 'AND', 'task')
        load = db.ex("SELECT date_trunc('minute', expenses.time), COALESCE(task.object, 'Расход без объекта'), "
                     "COALESCE(employee.name, employee.handle), amount, note FROM expenses LEFT JOIN task ON taskid = "
                     f"task.id JOIN employee ON employeeid = employee.id WHERE confirmed = True {period}")
        headers = 'Время;Объект;Сотрудник;Сумма;Заметка\n'
    else:
        period = period_handler(call_data, 10, 'AND', 'task')
        load = db.ex(
            "SELECT date_trunc('minute', time), task.object, COALESCE(employee.name, employee.handle), income FROM"
            "employeetotask JOIN employee ON employeeid = employee.id JOIN task ON taskid = task.id WHERE main ="
            "True" + period)
        headers = 'Время;Объект;Сотрудник;Сумма\n'
    if not load:
        bot.send_message(id_user, 'Записей за данный период не найдено')
    else:
        csv_str = csv_creator(headers, load)
        bot.send_document(id_user, io.BytesIO(csv_str.encode()),
                          visible_file_name=f'{"Расходы" if expense else "Доходы"}.csv')
        bot.send_document(id_user, io.BytesIO(csv_str.encode('cp1251')),
                          visible_file_name=f'{"Расходы" if expense else "Доходы"}-1251.csv')


def insert_digit(message, direction, note, func):
    try:
        digit = func(message.text.replace(',', '.'))
        stack[message.chat.id][direction] = digit
        if note:
            bot.send_message(message.chat.id, note)
    except ValueError:
        bot.send_message(
            message.chat.id, 'Число введено некорректно, попробуйте еще раз')


def coalesce(array):
    try:
        digit = int(array[0][0])
        return digit
    except (IndexError, TypeError, ValueError):
        return 0


def get_auto_list():
    car_list = db.ex(
        'SELECT id, name, color, licensenum FROM auto WHERE deleted IS NOT True')
    if car_list:
        car_list = '\n'.join([' '.join([str(obj) for obj in item])
                              for item in car_list])
    else:
        car_list = 'Список авто пуст'
    return car_list


def get_employees(coeff, admin):
    employee_list = db.ex(
        f'''SELECT id, name {', role' if admin else ''} {', coeff, wage' if coeff else ''} '''
        f'''FROM employee WHERE deleted IS NOT TRUE {"AND role != 'owner'" if not admin else ''} '''
        f'''AND name IS NOT NULL ORDER BY 1''')
    if employee_list:
        employee_list = '\n'.join(
            [' '.join([str(obj) for obj in item]) for item in employee_list])
    else:
        employee_list = 'Список сотрудников пуст'
    unnamed_employee = db.ex(
        f'''SELECT id, handle {', role' if admin else ''} FROM employee WHERE deleted IS NOT TRUE AND name IS NULL '''
        f'''{"AND role != 'owner'" if not admin else ''}''')
    if unnamed_employee:
        unnamed_employee = '\n'.join(
            [' '.join([str(obj) for obj in item]) for item in unnamed_employee])
        unnamed_employee = '\nВ базе также есть несколько сотрудников с неподтвержденным именем:\n' + unnamed_employee
    else:
        unnamed_employee = ''
    headers = 'id, имя, роль, коэф, З/П\n' if admin else ''
    return headers + (employee_list + unnamed_employee).replace('user', 'сотрудник').replace('owner', 'администратор')


def get_time_range():
    now = dt.datetime.now()
    first_period_start = now.replace(day=1)
    first_period_end = first_period_start + dt.timedelta(days=14)
    pre_period_start = (first_period_start - dt.timedelta(days=1)).replace(day=1) + dt.timedelta(days=15)
    pre_period_end = first_period_start - dt.timedelta(days=1)
    second_period_start = first_period_end + dt.timedelta(days=1)
    second_period_end = now.replace(month=(now.month + 1) % 12) - dt.timedelta(days=1)
    post_period_start = now.replace(month=(now.month + 1) % 12)
    post_period_end = post_period_start + dt.timedelta(days=14)
    return [pre_period_start, pre_period_end,
            first_period_start, first_period_end,
            second_period_start, second_period_end,
            post_period_start, post_period_end]


def upload_picture(message, section, folder):
    file = bot.get_file(message.photo[-1].file_id)
    file = bot.download_file(file.file_path)
    addurl = f"resources?path={section}{folder}"
    r = requests.put(baseurl + addurl, headers=yandex_headers)
    if r.status_code not in (201, 409):
        return False
    addurl = f"resources/upload?path={section}{folder}%2F{message.chat.first_name} {secrets.token_urlsafe(4)}"
    r = requests.get(baseurl + addurl, headers=yandex_headers)
    if r.status_code != 200:
        return False
    r = json.loads(r.text)
    files = {'file': file}
    r = requests.put(r['href'], headers=yandex_headers, files=files)
    return r.status_code == 201


@bot.message_handler(func=lambda message: stack_filter(message, 'userPictureTrip'), content_types=['text', 'photo'])
def upload_trip_report(message):
    data = stack[message.chat.id].get('userPictureTripData', None)
    if data:
        if upload_picture(message, constants.TRIPREPORTFOLDER, f'{data[0][1].strftime("%Y-%m-%d")} {data[0][0]}'):
            bot.send_message(message.chat.id,
                             'Фото успешно загружено\n'
                             'Для загрузки еще одного фото по этому же'
                             ' объекту просто отправьте его в чат\n'
                             'Если вы закончили загружать фотографии - '
                             'обязательно нажмите на кнопку ниже',
                             reply_markup=mk.createMarkup(1,
                                                          ['Закончить'],
                                                          ['endPictureUploading']))
        else:
            bot.send_message(message.chat.id, 'С загрузкой фото произошла ошибка :(\n'
                                              'Попробуйте еще раз или обратитесь к администратору',
                             reply_markup=mk.createMarkup(1,
                                                          ['Закончить'],
                                                          ['endPictureUploading']))
        return
    try:
        trip_id = int(message.text)
    except ValueError:
        bot.send_message(message.chat.id,
                         'Номер поездки введен некорректно, попробуйте еще раз')
        return
    trip_object = db.ex('SELECT object, time FROM task WHERE id = %s', (trip_id,))
    if not trip_object:
        bot.send_message(message.chat.id,
                         'Поездки с таким номером не найдено, попробуйте еще раз')
        return
    stack[message.chat.id]['userPictureTripData'] = trip_object
    bot.send_message(message.chat.id, 'Отлично, теперь отправьте фото для загрузки')


@bot.message_handler(func=lambda message: stack_filter(message, 'userPictureAccountData'),
                     content_types=['photo'])
def upload_account_report(message):
    if upload_picture(message, constants.ACCOUNTREPORTFOLDER, stack[message.chat.id]['userPictureAccountData']):
        bot.send_message(message.chat.id,
                         'Фото успешно загружено\n'
                         'Для загрузки еще одного фото по этому же'
                         ' объекту просто отправьте его в чат\n'
                         'Если вы закончили загружать фотографии - '
                         'обязательно нажмите на кнопку ниже',
                         reply_markup=mk.createMarkup(1,
                                                      ['Закончить'],
                                                      ['endPictureUploading']))
    else:
        bot.send_message(message.chat.id, 'С загрузкой фото произошла ошибка :(\n'
                                          'Попробуйте еще раз или обратитесь к администратору',
                         reply_markup=mk.createMarkup(1,
                                                      ['Закончить'],
                                                      ['endPictureUploading']))


@bot.message_handler(commands=['start'])
def start_handler(message):
    bot.send_message(message.chat.id,
                     'Добро пожаловать!\nДля авторизации как сотрудник отправьте команду /authuser\nДля авторизации '
                     'как администатор отправьте команду /authowner\nВашу заявку должен подтвердить администратор')


@bot.message_handler(commands=['office'])
def office_handler(message):
    get_role = db.ex('SELECT role FROM employee WHERE chatid = %s AND deleted IS NOT True',
                     (int(message.chat.id),))
    logging.info(f'{message.chat.first_name} got into officeHandler: getRole is {get_role}')
    if not get_role:
        bot.send_message(
            message.chat.id,
            'Такой пользователь не зарегистрирован в системе\nОбратитесь к администратору\n/authuser для авторизации')
    elif get_role[0][0] == 'owner':
        bot.send_message(message.chat.id,
                         "Личный кабинет администратора",
                         reply_markup=mk.createMarkup(2,
                                                      ['Автомобили\U0001f690',
                                                       'Сотрудники\U0001f468',
                                                       'Затраты\U0001f4b0',
                                                       'Доходы\U0001f3e6',
                                                       'Сводка\U0001f4c8',
                                                       'Выдать З/П\U0001f4b8',
                                                       'Поездки\U0001f6e3\uFE0F',
                                                       'Зарплата\U0001f4b5',
                                                       'Подтвердить расходы\U0001f4dd'],
                                                      [
                                                          'adAuto',
                                                          'adEmployee',
                                                          'adExpenses',
                                                          'adIncome',
                                                          'adPivot',
                                                          'adWage',
                                                          'adObjects',
                                                          'adLoadWage',
                                                          'adApproveExpenses']))
    elif get_role[0][0] == 'user':
        bot.send_message(message.chat.id,
                         'Личный кабинет сотрудника\nДля загрузки фотоотчета просто отправьте фотографию боту',
                         reply_markup=mk.createMarkup(
                             1,
                             ['Отчитаться о поездке\U0001f4dd',
                              'Мои доходы\U0001f4b0',
                              'Учесть расход\U0001f4b8',
                              'Загрузить фотоотчет\U0001f4f7'],
                             ['userTask',
                              'userIncome0',
                              'userAddExpense',
                              'userPicture']))
    else:
        bot.send_message(
            message.chat.id, 'Проблемы с ролью пользователя\nОбратитесь к администратору')
    clear_user_stack(message.chat.id)


@bot.message_handler(commands=['authuser', 'authowner'])
def auth(message):
    role = message.text[5:]
    current_role = db.ex(
        'SELECT role, deleted  FROM employee WHERE chatid = %s', (message.chat.id,))
    logging.info(f'{message.chat.first_name} got into authHandler using {message.text}: current role is {current_role}')
    if current_role and (current_role[0][0] == role or current_role[0][1]):
        bot.send_message(message.chat.id, 'Вы уже авторизованы')
        return
    for owner in db.ex("SELECT chatid FROM employee WHERE role = 'owner'"):
        bot.send_message(owner[0],
                         f'Новый запрос на авторизацию пользователя от '
                         f'{message.chat.first_name if message.chat.first_name else ""} '
                         f'{message.chat.last_name if message.chat.last_name else ""}\n@'
                         f'{message.chat.username}\nЗапрашиваемая роль: {rolemapping[role]}',
                         reply_markup=mk.createMarkup(
                             1,
                             ['Авторизовать'],
                             [f'auth//'
                              f'{message.chat.username if message.chat.username else f"{message.chat.first_name}"}'
                              f'//{message.chat.id}//{role}//{owner[0]}']))
    bot.send_message(
        message.chat.id, 'Запрос на авторизацию успешно отправлен, ожидайте ответа администратора')


@bot.message_handler(func=lambda message: stack_filter(message, 'creatingTask') or message.text == '/skip')
def create_task(message):
    if not stack[message.chat.id]['taskObject']:
        try:
            id_object = int(message.text)
            objectNameGot = db.ex(
                'SELECT object FROM task WHERE id = %s', (id_object,))[0][0]
            stack[message.chat.id]['taskObject'] = objectNameGot
        except ValueError:
            stack[message.chat.id]['taskObject'] = message.text
        logging.info(f"createTask:{message.chat.first_name}:{message.text}:{stack[message.chat.id]['taskObject']}")
        car_list = get_auto_list()
        bot.send_message(
            message.chat.id,
            'Теперь введите номер(цифру перед названием) автомобиля, на котором была совершена поездка\n' + car_list)
    elif not stack[message.chat.id]['taskCar']:
        try:
            id_car = int(message.text)
            if not db.ex('SELECT * FROM auto WHERE id = %s', (id_car,)):
                bot.send_message(
                    message.chat.id, 'Машины с таким id не найдено в базе, попробуйте еще раз')
            else:
                stack[message.chat.id]['taskCar'] = id_car
                employee_list = get_employees(coeff=False, admin=False)
                bot.send_message(
                    message.chat.id,
                    'Отлично, теперь введите номера напарников, с которым вы выполняли задачу\nЕсли вы выполняли ее '
                    'самостоятельно, то отправьте слово /skip\n\n' + employee_list + f'\n\nомера напарников нужно '
                                                                                     f'вводить одним сообщением через '
                                                                                     f'пробел:\n2 4 16 17 9')
        except ValueError:
            bot.send_message(
                message.chat.id, 'Число введено некорректно, попробуйте еще раз')
        logging.info(f"createTask:{message.chat.first_name}:{message.text}:{stack[message.chat.id]['taskCar']}")
    elif not stack[message.chat.id]['taskBuddy']:
        if message.text == '/skip':
            stack[message.chat.id]['taskBuddy'] = 'flagSkipped'
            bot.send_message(
                message.chat.id, 'Отлично, теперь введите количество километров, затраченных на поездку')
        else:
            data = []
            try:
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
            bot.send_message(
                message.chat.id, 'Супер, теперь введите количество километров, затраченных на поездку')
        logging.info(f"createTask:{message.chat.first_name}:{message.text}:{stack[message.chat.id]['taskBuddy']}")
    elif not stack[message.chat.id]['taskKm']:
        insert_digit(message, 'taskKm',
                     'Отлично, теперь введите количество часов, которое заняла поездка', int)
        logging.info(f"createTask:{message.chat.first_name}:{message.text}:{stack[message.chat.id]['taskKm']}")
    elif not stack[message.chat.id]['taskTime']:
        insert_digit(message, 'taskTime',
                     'Теперь введите сумму, полученную за заказ', int)
        logging.info(f"createTask:{message.chat.first_name}:{message.text}:{stack[message.chat.id]['taskTime']}")
    elif not stack[message.chat.id]['taskIncome']:
        insert_digit(message, 'taskIncome',
                     'Теперь нужно отчитаться о связанных с поездкой расходах\nКаждую статью расходов нужно описать '
                     'отдельным сообщением в следующей форме: \n\n1500 на бензин\n300 на мобильную связь\n\nКогда вы '
                     'укажете все расходы(или если они отсутствуют), отправьте команду /skip',
                     float)
        logging.info(f"createTask:{message.chat.first_name}:{message.text}:{stack[message.chat.id]['taskIncome']}")
    elif not stack[message.chat.id]['taskExpensesFinished']:
        if message.text == '/skip':
            logging.info(
                f"createTask:{message.chat.first_name}:{message.text}:{stack[message.chat.id]['taskExpenses']}")
            stack[message.chat.id]['taskExpensesFinished'] = True
            idTask = db.ex(
                'INSERT INTO task(object, car, kmspent, hoursspent, income, time) VALUES (%s, %s, %s, %s, %s, '
                'NOW()) RETURNING *',
                (stack[message.chat.id]['taskObject'], stack[message.chat.id]['taskCar'],
                 stack[message.chat.id]['taskKm'], stack[message.chat.id]['taskTime'],
                 stack[message.chat.id]['taskIncome']))[0][0]
            idTaskMaker = db.ex(
                'SELECT id FROM employee WHERE chatid = %s', (message.chat.id,))[0][0]
            db.ex('INSERT INTO employeetotask(employeeid, taskid, main) VALUES(%s, %s, True)',
                  (idTaskMaker, idTask))
            if stack[message.chat.id]['taskBuddy'] != 'flagSkipped':
                for buddy_id in stack[message.chat.id]['taskBuddy']:
                    db.ex(
                        'INSERT INTO employeetotask(employeeid, taskid, main) VALUES (%s, %s, False) ON CONFLICT DO '
                        'NOTHING',
                        (buddy_id, idTask))
            if stack[message.chat.id]['taskExpenses']:
                for expense in stack[message.chat.id]['taskExpenses']:
                    db.ex('INSERT INTO expenses(taskid, employeeid, amount, note) VALUES (%s, %s, %s, %s)',
                          (idTask, idTaskMaker, expense[0], expense[1]))
            logging.info(f"createTask:{message.chat.first_name}:Task created")
            bot.send_message(
                message.chat.id, 'Готово! Отчет успешно внесен в базу\n/office для перехода в личный кабинет')
            clear_user_stack(message.chat.id)
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
        clear_user_stack(message.chat.id)
        bot.send_message(
            message.chat.id,
            'С отчетом о поездке произошла ошибка :(\nПерейдите в личный кабинет /office и попробуйте еще раз')


@bot.message_handler(func=lambda message: stack_filter(message, 'addingAuto'))
def adding_auto(message):
    logging.info(f'addingAuto:{message.chat.first_name}:{message.text}')
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


@bot.message_handler(func=lambda message: stack_filter(message, 'deletingAuto', mustbedigit=True))
def deleting_auto(message):
    logging.info(f'deletingAuto:{message.chat.first_name}:{message.text}')
    db.ex('UPDATE auto SET deleted = True WHERE id = %s',
          param=(int(message.text),))
    bot.send_message(message.chat.id, f'Машина {message.text} удалена из базы', reply_markup=mk.createMarkup(
        2, ['Удалить еще', 'Закончить'], ['adAutoDelete', 'endAutoDelete']))


@bot.message_handler(func=lambda message: stack_filter(message, 'updateEmployee'))
def adding_employee(message):
    logging.info(f"addingExepnse:{message.chat.first_name}:{message.text}:{stack[message.chat.id]['updateEmployeeId']}")
    if not stack[message.chat.id]['updateEmployeeId']:
        insert_digit(message, 'updateEmployeeId',
                     'Теперь введите имя для сотрудника', int)
    elif not stack[message.chat.id]['updateEmployeeName']:
        stack[message.chat.id]['updateEmployeeName'] = message.text
        bot.send_message(
            message.chat.id,
            'Теперь введите коэффициент зарплаты для сотрудника '
            '(введите 1, чтобы оставить сотрудника без коэффициента)')
    elif not stack[message.chat.id]['updateEmployeeCoeff']:
        insert_digit(message, 'updateEmployeeCoeff',
                     'Отлично, теперь введите часовую ставку сотрудника', float)
    elif not stack[message.chat.id]['updateEmployeeWage']:
        insert_digit(message, 'updateEmployeeWage', None, int)
        db.ex('UPDATE employee SET name = %s, coeff = %s, wage = %s WHERE id = %s',
              (stack[message.chat.id]['updateEmployeeName'], stack[
                  message.chat.id]['updateEmployeeCoeff'], stack[message.chat.id]['updateEmployeeWage'],
               stack[message.chat.id]['updateEmployeeId']))
        bot.send_message(message.chat.id, 'Готово! Информация о сотруднике отредактирована',
                         reply_markup=mk.createMarkup(
                             2, ['Обновить еще', 'Закончить'], ['adEmployeeUpdate', 'endEmployeeUpdate']))


@bot.message_handler(func=lambda message: stack_filter(message, 'deletingEmployee', mustbedigit=True))
def deleting_employee(message):
    logging.info(f'deletingEmployee:{message.chat.first_name}:{message.text}')
    db.ex('UPDATE employee SET deleted = True WHERE id = %s', param=(message.text,))
    bot.send_message(message.chat.id, f'Сотрудник {message.text} удален из базы', reply_markup=mk.createMarkup(
        2, ['Удалить еще', 'Закончить'], ['adEmployeeDelete', 'endEmployeeDelete']))


@bot.message_handler(func=lambda message: stack_filter(message, 'userAddExpense'))
def adding_expense(message):
    logging.info(f'addingExepnse:{message.chat.first_name}:{message.text}')
    try:
        data = message.text.split()
        amount = int(data[0])
        caption = ' '.join(data[1:])
        if not caption:
            raise IndexError
        db.ex(
            'INSERT INTO expenses(employeeid, amount, note) VALUES ((SELECT id FROM employee WHERE chatid = %s), %s, '
            '%s)',
            (message.chat.id, amount, caption))
    except ValueError:
        bot.send_message(message.chat.id,
                         'Сумма расхода введена в неверном формате, попробуйте еще раз\nШаблон отчета о расходах: '
                         '\n1500 на бензин\n300 на мобильную связь')
    except IndexError:
        bot.send_message(message.chat.id,
                         'Назначение расхода введено неверно, попробуйте еще раз\nШаблон отчета о расходах: \n1500 на '
                         'бензин\n300 на мобильную связь')
    else:
        stack[message.chat.id]['userAddExpense'] = False
        bot.send_message(message.chat.id, 'Расход успешно учтен',
                         reply_markup=mk.createMarkup(1, ['Добавить еще', 'Закончить'],
                                                      ['userAddExpense', 'userAddExpenseEnd']))


@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    logging.info(f'callback {call.data}:{call.from_user.first_name}')
    clear_user_stack(call.from_user.id)
    if call.data.startswith('auth'):
        data = call.data.split('//')
        db.ex(
            'INSERT INTO employee(handle, chatid, role) VALUES (%s, %s, %s) ON CONFLICT (chatid) DO UPDATE SET role = '
            '%s, deleted = NULL WHERE employee.chatid = %s',
            (data[1], int(data[2]), data[3], data[3], int(data[2])))
        bot.send_message(
            data[2],
            f'Ваши привилегии обновлены\nНовая роль: {rolemapping[data[3]]}\n/office для перехода в личный кабинет')
        bot.edit_message_text(
            f'Роль пользователя {data[1]} успешно обновлена\nНовая роль {rolemapping[data[3]]}', call.from_user.id,
            call.message.id,
            reply_markup=None)
    elif call.data == "adAuto":
        autoList = get_auto_list()
        bot.edit_message_text('Список авто:\n' + autoList, call.from_user.id, call.message.id,
                              reply_markup=mk.createMarkup(2, ['Добавить', 'Удалить'], ['adAutoAdd', 'adAutoDelete']))
    elif call.data == "adAutoAdd":
        stack[call.from_user.id]['addingAuto'] = True
        stack[call.from_user.id]['addingAutoName'] = None
        stack[call.from_user.id]['addingAutoColor'] = None
        bot.edit_message_text('Добавляем автомобиль в базу\nВведите название автомобиля', call.from_user.id,
                              call.message.id)
    elif call.data == "endAutoAdd":
        stack[call.from_user.id]['addingAuto'] = False
        bot.send_message(
            call.from_user.id, 'Добавление закончено\n/office для входа в личный кабинет')
    elif call.data == "adAutoDelete":
        bot.edit_message_text('Введите номер автомобиля, который желаете удалить из базы', call.from_user.id,
                              call.message.id)
        stack[call.from_user.id]['deletingAuto'] = True
    elif call.data == "endAutoDelete":
        stack[call.from_user.id]['deletingAuto'] = False
        bot.send_message(
            call.from_user.id, 'Удаление автомобилей закончено\n/office для входа в личный кабинет')
    elif call.data == "adEmployee":
        employeeList = get_employees(coeff=True, admin=True)
        bot.edit_message_text('Список сотрудников:\n' + employeeList, call.from_user.id, call.message.id,
                              reply_markup=mk.createMarkup(1, ['Обновить информацию', 'Удалить'],
                                                           ['adEmployeeUpdate', 'adEmployeeDelete']))
    elif call.data == "adEmployeeUpdate":
        bot.edit_message_text(
            'Введите номер сотрудника, информацию о котором собираетесь редактировать\n\n' + call.message.text,
            call.from_user.id, call.message.id)
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
        bot.edit_message_text('Введите номер сотрудника, которого желаете удалить из базы\n\n' + call.message.text,
                              call.from_user.id,
                              call.message.id)
        stack[call.from_user.id]['deletingEmployee'] = True
    elif call.data == "endEmployeeDelete":
        stack[call.from_user.id]['deletingEmployee'] = False
        bot.send_message(
            call.from_user.id, 'Удаление сотрудников закончено\n/office для входа в личный кабинет')
    elif call.data == "adExpenses":
        bot.edit_message_text('Выберите период выгрузки расходов', call.from_user.id, call.message.id,
                              reply_markup=mk.createMarkup(
                                  2, ['24 часа', 'Неделя', 'Месяц', 'Все время'],
                                  ['loadExpenses1', 'loadExpenses7', 'loadExpenses30', 'loadExpensesAll']))
    elif call.data.startswith('loadExpenses'):
        csv_load_sender(call.from_user.id, True, call.data)
    elif call.data == "adIncome":
        bot.edit_message_text('Выберите период выгрузки доходов', call.from_user.id, call.message.id,
                              reply_markup=mk.createMarkup(
                                  2, ['24 часа', 'Неделя', 'Месяц', 'Все время'],
                                  ['loadIncome1', 'loadIncome7', 'loadIncome30', 'loadIncomeAll']))
    elif call.data.startswith('loadIncome'):
        csv_load_sender(call.from_user.id, False, call.data)
    elif call.data == 'adPivot':
        bot.edit_message_text('Выберите период выгрузки', call.from_user.id, call.message.id,
                              reply_markup=mk.createMarkup(
                                  2, ['24 часа', 'Неделя', 'Месяц', 'Все время'],
                                  ['loadPivot1', 'loadPivot7', 'loadPivot30', 'loadPivotAll']))
    elif call.data.startswith('loadPivot'):
        period = period_handler(call.data, 9, 'WHERE', 'task')
        income = db.ex('SELECT sum(income) FROM task ' + period)
        income = coalesce(income)
        period = period_handler(call.data, 9, 'AND', 'expenses')
        expenses = db.ex(
            f"SELECT sum(amount) FROM expenses WHERE confirmed = True {period}")
        expenses = coalesce(expenses)
        period = period_handler(call.data, 9, 'WHERE', 'payments')
        wage = db.ex(
            "SELECT sum(payments.amount) FROM payments JOIN employeetotask e on payments.employeetotaskid = e.id"
            f" JOIN task on taskid = task.id {period}"
        )
        wage = coalesce(wage)
        profit = income - expenses - wage
        if not period:
            pivot = 'Сводка за все время:\n'
        else:
            days = period.split("'")[1].split()[0]
            pivot = f'Сводка за {days} {"день" if int(days) == 1 else "дней"}\n'
        pivot = pivot + f"Доходы: {income}\nРасходы: {expenses}\nРасходы на З/П: {wage}\nПрибыль: {profit}"
        bot.edit_message_text(pivot, call.from_user.id, call.message.id)
    elif call.data == 'adWage':
        bot.edit_message_text(
            'Администратору предстоит подтвердить совершенные поездки и начислить за них заработную '
            'плату сотрудникам\nЗарплата подтверждается только для сотрудников с установленой часовой '
            'ставкой', call.from_user.id, call.message.id,
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
        load = db.ex(
            'SELECT COALESCE(name, handle), object, hoursspent, hoursspent * wage * coeff, employeetotask.id AS sum '
            'FROM employeetotask JOIN employee ON employeeid = employee.id JOIN task ON taskid = task.id WHERE paid '
            'IS NULL AND wage IS NOT NULL LIMIT 1;')
        if load:
            employeeToTaskId = load[0][4]
            amount = load[0][3]
            load = f'Выплата для сотрудника {load[0][0]} за поездку на объект {load[0][1]}\nЗатрачено часов: ' \
                   f'{load[0][2]}\nВыплата: {int(load[0][3])}'
            bot.edit_message_text(load, call.from_user.id, call.message.id,
                                  reply_markup=mk.createMarkup(1, ['Подтвердить выплату', 'Отклонить выплату'], [
                                      f'adWageStartApply//{employeeToTaskId}//{amount}',
                                      f'adWageStartReject//{employeeToTaskId}']))
        else:
            bot.edit_message_text('Не найдено неоплаченных поездок\n/office', call.from_user.id, call.message.id)
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
        last_object = db.ex(
            'SELECT DISTINCT ON(object) id, object FROM task ORDER BY object, time DESC;')
        if not last_object:
            queryText = 'Заполняем задачу\nДля начала введите название объекта:'
        else:
            last_object = '\n'.join(
                [' '.join([str(obj) for obj in item]) for item in last_object])
            queryText = 'Заполняем задачу\nВведите название нового объекта или пришлите номер одного из ' \
                        'представленных:\n\n' + last_object
        bot.edit_message_text(queryText, call.from_user.id, call.message.id)
    elif call.data.startswith('userIncome'):
        period = int(call.data[10:])
        load = db.ex(
            f"SELECT sum(amount) FROM payments JOIN employeetotask ON employeetotaskid = employeetotask.id WHERE "
            f"employeeid = (SELECT id FROM employee WHERE chatid = %s) AND date_trunc('month', NOW()) -"
            f" INTERVAL '{period} month'  = date_trunc('month', time);",
            (call.from_user.id,))
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
        monthNum = (dt.datetime.today() - dt.timedelta(days=period * 30)).month
        bot.send_message(call.from_user.id,
                         f'Доходы за {month[monthNum - 1]}\n{load}', reply_markup=markup)
    elif call.data == 'userAddExpense':
        bot.edit_message_text('Каждую статью расходов нужно описать отдельным сообщением в следующей форме:\nсумма '
                              'расхода+пробел+назначение расхода \n\n1500 на бензин\n300 на мобильную связь',
                              call.from_user.id, call.message.id)
        stack[call.from_user.id]['userAddExpense'] = True
    elif call.data == "userAddExpenseEnd":
        stack[call.from_user.id]['userAddExpense'] = False
        bot.send_message(
            call.from_user.id, 'Внесение расходов завершено\n/office для входа в личный кабинет')
    elif call.data == 'adObjects':
        load = db.ex(
            "SELECT task.id, date_trunc('minutes', time), object, (SELECT name FROM employeetotask JOIN employee ON "
            "employeeid = employee.id WHERE task.id = taskid AND main = true), (SELECT name FROM employeetotask JOIN "
            "employee ON employeeid = employee.id WHERE task.id = taskid AND main = false), auto.name, kmspent, "
            "hoursspent, income, (SELECT sum(amount) FROM expenses WHERE taskid = task.id AND confirmed = True) FROM "
            "task JOIN auto ON task.car = auto.id;")
        if not load:
            bot.send_message(call.from_user.id, 'Поездок не найдено')
        else:
            bot.send_document(call.from_user.id, csv_creator(
                'ID;Дата;Объект;Сотрудник;Напарник;Авто;Километраж;Длительность;Доход;Расход\n', load),
                              visible_file_name='Поездки.csv')
    elif call.data.startswith('adLoadWage'):
        if call.data == 'adLoadWage':
            bot.edit_message_text('Выберите период выгрузки транзакций З/П', call.from_user.id, call.message.id,
                                  reply_markup=mk.createMarkup(
                                      2, ['24 часа', 'Неделя', 'Месяц', 'Все время'],
                                      ['adLoadWage1', 'adLoadWage7', 'adLoadWage30', 'adLoadWageAll']))
        else:
            period = period_handler(call.data, 10, 'WHERE', 'payments')
            if db.ex("SELECT COUNT(*) FROM employee WHERE name IS NULL")[0][0] != 0:
                bot.send_message(call.from_user.id,
                                 'Часть имен сотрудников не подтверждена, информация о выплатах может отображаться '
                                 'некорректно\nЧтобы избежать этого, обновите информацию о сотрудниках')
            load = db.ex(
                "SELECT employee.name, sum(amount) FROM payments JOIN employeetotask "
                "ON employeetotask.id = employeetotaskid JOIN employee "
                f"ON employeeid = employee.id {period} GROUP BY employee.name")
            if not load:
                bot.edit_message_text('Выплат за данный период не найдено',
                                      call.from_user.id, call.message.id)
            else:
                bot.send_document(call.from_user.id, csv_creator(
                    'Сотрудник;Выплата\n', load),
                                  visible_file_name='Зарплаты.csv')
    elif call.data.startswith('adApproveExpenses'):
        if call.data != 'adApproveExpenses':
            db.ex('UPDATE expenses SET confirmed = %s WHERE id = %s',
                  (call.data[17:].startswith('Acc'), call.data[20:]))
        load = db.ex(
            "SELECT expenses.id, COALESCE(task.object, 'Расход без объекта'), COALESCE(employee.name, "
            "employee.handle), amount, note, date_trunc('minute', expenses.time) FROM expenses LEFT JOIN task ON "
            "task.id = taskid JOIN employee ON employeeid = employee.id WHERE confirmed IS NULL LIMIT 1; ")
        if not load:
            bot.edit_message_text(
                'Неподтвержденных расходов не найдено\n'
                '/office для перехода в личный кабинет',
                call.from_user.id, call.message.id)
        else:
            bot.edit_message_text(
                f'Поездка: {load[0][1]}\nСотрудник:'
                f' {load[0][2]}\nСумма: {load[0][3]}\nЦель расхода: '
                f'{load[0][4]}\n{load[0][5]}',
                call.from_user.id,
                call.message.id,
                reply_markup=mk.createMarkup(
                    1, ['Подтвердить', 'Отклонить'],
                    [f'adApproveExpensesAcc{load[0][0]}',
                     f'adApproveExpensesRej{load[0][0]}']))
    elif call.data.startswith('userPicture'):
        if call.data.endswith('Picture'):
            bot.edit_message_text('Какой отчет вы желаете загрузить?',
                                  call.from_user.id,
                                  call.message.id,
                                  reply_markup=mk.createMarkup(
                                      1,
                                      ['Акт выполненных работ',
                                       'Отчет о движении средств'],
                                      ['userPictureTrip',
                                       'userPictureAccount']
                                  ))
        elif call.data.endswith('Trip'):
            if call.data == 'userPictureTrip':
                objects = db.ex("SELECT id, object, date_trunc('minute', time) FROM task WHERE "
                                "time >= NOW() - INTERVAL '30 day' ORDER BY time DESC")
                objects = '\n'.join(
                    [' '.join([str(obj) for obj in item]) for item in objects])
                stack[call.from_user.id]['userPictureTrip'] = True
                bot.edit_message_text(f'Пришлите номер поездки, о которой'
                                      f' вы хотите отчитаться\n\n{objects}',
                                      call.from_user.id,
                                      call.message.id)
        elif call.data.endswith('Account'):
            periods = get_time_range()
            periods = [i.strftime("%d.%m.%Y") for i in periods]
            periods = ['-'.join(periods[i:i + 2]) for i in range(0, len(periods), 2)]
            bot.edit_message_text('Выберите отчетный период',
                                  call.from_user.id,
                                  call.message.id,
                                  reply_markup=mk.createMarkup(
                                      1,
                                      periods,
                                      [f'userPictureAccount//{i}' for i in periods]
                                  ))
        else:
            stack[call.from_user.id]['userPictureAccountData'] = call.data[20:]
            bot.edit_message_text('Отлично, отправьте фото для загрузки',
                                  call.from_user.id,
                                  call.message.id,
                                  reply_markup=mk.createMarkup(
                                      1,
                                      ['Отменить загрузку фото'],
                                      ['endPictureUploading']
                                  ))
    elif call.data == 'endPictureUploading':
        bot.edit_message_text('Перейти в /office',
                              call.from_user.id,
                              call.message.id)


def main():
    logging.info('Polling started')
    bot.infinity_polling()


if __name__ == '__main__':
    main()
