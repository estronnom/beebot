import psycopg2

class dbHandler():
    def __init__(self, params):
        self.conn = psycopg2.connect(**params)
        self.cur = self.conn.cursor()

    def __del__(self):
        self.conn.commit()
        self.cur.close()
        self.conn.close()

    def ex(self, query, param=None):
        try:
            if not param:
                self.cur.execute(query)
            else:
                self.cur.execute(query, param)
        except Exception as exc:
            self.conn.commit()
            print(exc)
            return
        try:
            self.conn.commit()
            return self.cur.fetchall()
        except:
            pass
