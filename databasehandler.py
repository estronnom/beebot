import psycopg2
import psycopg2.errors


class DatabaseHandler:
    def __init__(self, params):
        self.params = params
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
        except Exception as exc:
            print(exc)
            if not retry:
                try:
                    self.conn = psycopg2.connect(**self.params)
                    return self.ex(query, param, True)
                except psycopg2.errors as exc:
                    print(exc)
        finally:
            self.conn.commit()
            return self.cur.fetchall()