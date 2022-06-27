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
            if not param:
                self.cur.execute(query)
            else:
                self.cur.execute(query, param)
            self.conn.commit()
            return self.cur.fetchall()
        except Exception as exc:
            self.conn.commit()
            print(exc)
            if not retry:
                try:
                    self.__init__(self._params)
                    return self.ex(query, param, True)
                except psycopg2.errors as exc:
                    print(exc)
