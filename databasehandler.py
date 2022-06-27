import psycopg2
import psycopg2.errors


class DatabaseHandler:
    def __init__(self, params):
        self._params = params
        self.conn = psycopg2.connect(**params)
        self.cur = self.conn.cursor()

    def __del__(self):
        self.conn.commit()
        self.cur.close()
        self.conn.close()

    def ex(self, query, param=None, retry=False):
        try:
            self.cur.execute(query, param)
        except Exception as exc:
            self.conn.rollback()
            print(exc)
            if not retry:
                self.__init__(self._params)
                return self.ex(query, param, True)
        else:
            data = self.cur.fetchall()
            self.conn.commit()
            return data
