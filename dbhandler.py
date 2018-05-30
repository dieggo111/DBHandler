"DBHandler module"
import logging
import json
import os
import datetime
import pickle
from pydoc import locate
import yaml
import sqlalchemy
from sqlalchemy.orm import sessionmaker
try:
    from .models import meta
except (ModuleNotFoundError, ImportError):
    from models import meta

DEFAULT_MODEL = os.path.join("models", "default")
# define header names of incomming data
HEADER = "header"        # header name is mendatory
DATA_HEADER = ["data"]   # at least one data_header is mendatory

class DBHandler(object):
    """Database handling

    Methods:
        - load_cred:        loads credentials to access a mySQL DB
        - load_cfg:         loads cfg file with info about DB and its tables
        - get_dict:         returns table row
        - add_item:         adds dict to DB table
        - get_table_keys:   gets list of all DB table keys
        - get_values:       returns all values of key in DB table
        - check_for_value:  checks if value is in DB table or not
        - untangle_data:    untangles a data container and adjusts data so that
                            data can be added to respective table
        - upload_data:      uploads data container to DB
        - get_dbt:          returns DBTable object
        - get_session:      returns the session object
    """
    def __init__(self, db_cfg=None):
        """Load credentials, DB structure and name of DB map from cfg file,
           create DB session. Create DBTable object to get table names of DB
           from cfg file, import table classes and get name of primary keys.
           If no credentials are given, then a default SQlite DB file is
           created.

        Args:
            - db_cfg (yaml) : contains infos about DB structure and location of
                              DB credentials.
        Misc:
            - cred = {"host"      : "...",
			          "database"  : "...",
			          "user"      : "...",
			          "passwd"    : "..."}
        """
        self.log = logging.getLogger("mc." + __class__.__name__)
        self.log.setLevel(logging.DEBUG)
        self.log.info("DBHandler")
        stream = logging.StreamHandler()
        self.log.addHandler(stream)

        db_cfg = self.load_cfg(db_cfg)

        self.dbt = DBTable(map_file=db_cfg["map"],
                           table_dict=db_cfg["tables"],
                           cr_dict=db_cfg["cross-reference"])

        if db_cfg["engine"] == "sqlite":
            engine = sqlalchemy.create_engine("sqlite:///mySQlite.db")
            meta.BASE.metadata.create_all(engine, checkfirst=True)
            session = sessionmaker(bind=engine)
            self.session = session()
        elif db_cfg["engine"] == "mysql+mysqlconnector":
            cred = self.load_cred(db_cfg["credentials"])
            engine = sqlalchemy.create_engine(db_cfg["engine"]
                                              + "://"
                                              + cred["user"] + ":"
                                              + cred["passwd"] + "@"
                                              + cred["host"] + ":"
                                              + "3306" + "/"
                                              + cred["database"])
            session = sessionmaker(bind=engine)
            self.session = session()
        else:
            self.log.warning("Unkown engine in DB cfg...")

        self.table_ass = db_cfg["table assignment"]
        self.key_ass = db_cfg["key assignment"]
        self.meas_tk = db_cfg["measurement type key"]
        self.cross_ref = db_cfg["cross-reference"]

        if self.dbt.all_names() == []:
            self.log.warning("Import of table classes failed...")
        else:
            self.dbt.set_session(self.session)
            self.log.info("Connection to database established...")
            self.log.info("Imported table classes: %s",
                          ", ".join(self.dbt.all_names()))

    def load_cred(self, arg):
        """Handles the import of credentials"""
        try:
            cred = pickle.load(open(arg, "rb"))
            return cred
        except FileNotFoundError:             #pylint: disable = W0702
            self.log.error("Couldn't find or read credentials...")

    def load_cfg(self, db_cfg):
        """Handles the import of cfg dict."""
        try:
            if db_cfg is None:
                db_cfg = os.path.join(DEFAULT_MODEL,
                                      "default_DB.cfg")
            with open(db_cfg, "r") as cfg:
                db_cfg = yaml.load(cfg)
                cfg.close()
            return db_cfg
        except TypeError:
            assert isinstance(db_cfg, dict)
            return db_cfg
        except FileNotFoundError:
            self.log.error("Couldn't find default resources...")
            raise ImportError

    def get_dict(self, table, pk_value=None):
        """Returns dict with all key:value-pairs from table. To print a
        specific row pass its primary key value. Default is all rows of table.

        Args:
            - table (sqlalchemy.ext.declarative class/str) : table object
            - pk_value (type defined by table) : primary key value of item you
                                                 are looking for

        Returns:
            Dict or None if there's no item with that pk value.
        """
        result = []
        if isinstance(table, str):
            table = self.dbt.obj(table)
        if pk_value is not None:
            for col in self.session.query(table).\
            filter(getattr(table, self.dbt.primkey(table)) == pk_value):
                result = sqlalchemy.orm.attributes.instance_dict(col)
# first element is {'_sa_instance_state':sqlalchemy.orm.state.InstanceState...}
                result.pop('_sa_instance_state')
                return result
        pk_list = self.get_values(table, str(self.dbt.primkey(table)))
        if not isinstance(pk_list, list):
            pk_list = [pk_list]
        for item in pk_list:
            for col in self.session.query(table).\
            filter(getattr(table, self.dbt.primkey(table)) == item):
                result.append(sqlalchemy.orm.attributes.instance_dict(col))
        for item in result:
            item.pop('_sa_instance_state')
        return result

    def add_item(self, table, item, force_upload=True): #pylint: disable=R1710
        """Add item to DB table.

        Args:
            - table (sqlalchemy.ext.declarative class/str) : table object
            - item (dict) : dict containing keys:values according to DB table.
            - force_upload (bool) : if False then method checks if item already
                                    exists in DB table and rejects upload if
                                    that is the case.
        """
        if isinstance(table, str):
            table = self.dbt.obj(table)
        try:
            upload = True
            if force_upload is False:
                val_list = []
                for key, val in item.items():
                    if self.session.query(sqlalchemy.exists().where(\
                            getattr(table, key) == val)).scalar():
                        val_list.append(val)
                    if len(val_list) == len(item.values()):
                        upload = False
                        self.log.info("Item is already present in DB table")
                        return False
            if upload is True:
                self.session.add(table(**item))
                self.session.commit()
                return True
            # self.log.info("Item succesfully added to DB...")
        except Exception as err: # pylint: disable=W0703
            if "Session.rollback()" in str(err):
                pass
            else:
                self.log.info("Item could't be added to DB...")
                self.log.debug(err)
                self.log.debug(item)
                raise ValueError

    def update_value(self, table, attr, old_value, new_value):
        """Update old to new value of all items in a certain DB table.

        Args:
            - table (sqlalchemy.ext.declarative class/str) : table object
            - attr (str) : table attribute
            - old_value (type given by DB table) :
            - new_value (type given by DB table) : replace item value with
                                                   new value
        """
        if isinstance(table, str):
            table = self.dbt.obj(table)
        self.session.query(getattr(table, attr)).\
        filter(getattr(table, attr) == old_value).\
        update({getattr(table, attr) : new_value})


    def get_table_keys(self, table):
        """Retrieve a list of all keys of a DB table.

        Args:
            - table (sqlalchemy.ext.declarative class or str) : table object

        Returns:
            Table keys as list of strings.
        """
        if isinstance(table, str):
            table = self.dbt.obj(table)
        inst = sqlalchemy.inspect(table)
        keys = [c_attr.key for c_attr in inst.mapper.column_attrs]
        return keys

    def get_values(self, table, key, key_args=None):
        """Returns the values of a given key for all items in a DB table.

        Args:
            - table (sqlalchemy.ext.declarative class) : table object
            - key (str) : attribute name of key
            - key_args (dict) : 'filter_by' takes keyword arguments

        Returns:
            Value of key in table.
        """
        if isinstance(table, str):
            table = self.dbt.obj(table)
        values = []
        if not key_args:
            for val, in self.session.query(getattr(table, key)):
                values.append(val)
        else:
            for val, in self.session.query(getattr(table, key)).\
                    filter_by(**key_args):
                values.append(val)
        if len(values) == 1:
            return values[0]
        return values

    def check_for_value(self, table, key, value):
        """Checks if key:value-pair is in DB table, e.g. sensor name (key=name,
        value="sensor name").

        Args:
            - table (sqlalchemy.ext.declarative class) : table object
            - key (str)                 : name of column in table
            - value (type of DB entry)  : value of table entry

        Returns:
        	True if found, False if not.
        """
        if isinstance(table, str):
            table = self.dbt.obj(table)
        for val, in self.session.query(getattr(table, key)):
            if value == val:
                return True
        return False

    def add_cross_ref(self, meas_data):
        """Add DB table cross-references to data.
        """
        for table in meas_data:
            cross_ref = self.dbt.get_cr(table, meas_data)
            if is_nested(table, self.table_ass) is False:
                if cross_ref != {} and isinstance(meas_data[table], dict):
                    meas_data[table].update(cross_ref)
                elif cross_ref != {} and isinstance(meas_data[table], list) \
                        and meas_data[table] != []:
                    for table_data in meas_data[table]:
                        table_data.update(cross_ref)
            else:
                para = cross_ref[0]
                gen = id_gen(cross_ref[1])
                for table_data in meas_data[table]:
                    eyedee = next(gen)
                    for dic in table_data:
                        dic.update({para : eyedee})
        return meas_data

    def untangle_data(self, meas_dict):
        """Sorts elements of data container.
        1) extracts and removes measurement type element from meas_dict since
           it is not needed anymore
        2) relates given keys to their destination table as stated in
           table assignment
        3) renames keys or adds default data as stated in key assignment
        4) converts falsely interpreted elements (like dates into datetime)

        Args:
            - meas_dict :
        Return:
            dict{ {table name : dict{ ... } },  ...}
        """
        for key, val in meas_dict[HEADER].items():
            if key == self.meas_tk:
                meas_type = val
                break
        meas_dict[HEADER].pop(self.meas_tk)

        new_meas_dict = compare_dicts(meas_dict, self.table_ass)
        new_meas_dict = convert_keys(new_meas_dict, self.key_ass[meas_type])
        new_meas_dict = adjust_keys(new_meas_dict)

        return new_meas_dict

    def upload_data(self, data, option="upload only"):  # pylint: disable=R0912
        """Add measurement to DB. Sorts data, converts keys and values
        according to DB table specifications.

        Args:
            - data (JSON, dict) : can be dict, json string or json file:
                                  dict{"header" : { ... },
                                       "data"   : [ { ... }, ... ]}
             - option (str) : "upload only", "print only", "both", default is
                              "upload only" (this argument was added mainly for
                              debugging purposes)
        """
        if isinstance(data, dict):
            meas_data = data
        else:
            try:
                # data is json string
                meas_data = json.load(data)
            except TypeError:
                # data is json file
                meas_data = json.loads(data)

        meas_data = self.untangle_data(meas_data)
        # add missing table cross-reference key/values
        meas_data = self.add_cross_ref(meas_data)
        # add data:
        try:            #pylint: disable=R1702
            for table in meas_data:
                if self.dbt.opt(table) == "once":
                    if option in ["both", "upload only"]:
                        self.add_item(self.dbt.obj(table), meas_data[table])
                    elif option in ["both", "print only"]:
                        self.log.info(meas_data[table])
                elif self.dbt.opt(table) == "always" \
                        and is_nested(table, self.table_ass) is False:
                    for dic in meas_data[table]:
                        if option in ["both", "upload only"]:
                            self.add_item(self.dbt.obj(table), dic)
                        elif option in ["both", "print only"]:
                            self.log.info(dic)
                elif self.dbt.opt(table) == "always" \
                        and is_nested(table, self.table_ass) is True:
                    for lis in meas_data[table]:
                        for dic in lis:
                            if option in ["both", "upload only"]:
                                self.add_item(self.dbt.obj(table), dic)
                            elif option in ["both", "print only"]:
                                self.log.info(dic)
            if option in ["both", "upload only"]:
                self.log.info("Upload finished...")
        except ValueError:
            self.log.warning("Upload was not succesful...")

    def get_dbt(self):
        """Returns DBTable object.
        """
        return self.dbt

    def get_session(self):
        """Returns engine object"""
        return self.session


#########################################################
##################### DBTable Class #####################
#########################################################

class DBTable(object):
    """Class to simplify DB table handling.

    Methods:
        - obj : returns table class object
        - pk: returns primary key of table
        - opt: returns table option stated in cfg file
        - all_names: returns all table names
        - get_cr: returns table cross-reference key/value
    """
    def __init__(self, map_file, table_dict, cr_dict, session=None):
        """Initialize globals, import DB table classes and the CrossReference
        class.
        """
        self.log = logging.getLogger("DBHandler.DBTable")
        self.log.setLevel(logging.DEBUG)

        self.cr_dict = cr_dict

        self.db_tables = {}
        self.session = ""
        if session is not None:
            self.session = session
        for table, option in table_dict.items():
            table_class = locate(map_file + "." + table)
            if table_class is not None:
                primary_key = sqlalchemy.inspect(table_class).\
                              primary_key[0].name
                self.db_tables[table] = (table_class,
                                         primary_key,
                                         option.replace("upload=", ""))

    def set_session(self, session):
        """Set self.session after initializing the class object"""
        self.session = session

    def get_cr(self, table, data):          #pylint: disable=R1710
        """Returns cross-reference parameter of table. It's either queried and
        filtered by keywords or the latest entry. '{}' if no cross-reference.
        The cross-reference must be hard-coded and is defined in the
        'DBTableCrossReference' class.

        Args:
            - table (str) : name of DB table
            - data (dict) : data dict in case keyword values are
                            needed for query
        """
        try:
            info = self.cr_dict[table]
        except KeyError:
            return {}
        if info["keyword"] not in ["None", None, ""]:
            search_para = {}
            if isinstance(info["keyword"], str):
                search_para[info["keyword"]] \
                        = data[info["table name"]][info["keyword"]]
            if isinstance(info["keyword"], (tuple, list)):
                for key in info["keyword"]:
                    search_para[key] = data[info["table name"]][key]
            for val, in self.session.query(
                    getattr(self.db_tables[info["table name"]][0],
                            info["para"])).filter_by(**search_para):
                return {info["para"] : val}
        elif info["keyword"] in ["None", None, ""] \
                and info["para option"] == "latest":
            val = self.session.query(
                getattr(self.db_tables[info["table name"]][0],
                        info["para"])).order_by(sqlalchemy.\
                        desc(info["para"])).first()
            # in case it's the first upload
            if val is None:
                val = [0]
            return {info["para"] : val[0]+1}
        elif info["keyword"] in ["None", None, ""] \
                and info["para option"] == "ascending":
            val = self.session.query(
                getattr(self.db_tables[info["table name"]][0],
                        info["para"])).order_by(sqlalchemy.\
                        desc(info["para"])).first()
            # in case it's the first upload
            if val is None:
                val = [0]
            return (info["para"], val[0])

    def obj(self, table):
        """Returns class object of table.
        """
        try:
            return self.db_tables[table][0]
        except KeyError:
            self.log.warning("Unkown table name...")

    def primkey(self, table):
        """Returns primary key of table.
        """
        try:
            if not isinstance(table, str):
                table = table.__name__
            return self.db_tables[table][1]
        except KeyError:
            self.log.warning("Unkown table name...")

    def opt(self, table):
        """Returns upload option of table.
        """
        try:
            if not isinstance(table, str):
                table = table.__name__
            return self.db_tables[table][2]
        except KeyError:
            self.log.warning("Unkown table name...")

    def all_names(self):
        """Returns list of names of all tables.
        """
        names = []
        for name in self.db_tables:
            names.append(name)
        return names


#########################################################
####################### Functions #######################
#########################################################



def is_nested(table, tab_ass):
    """Returns 'True' if the data is nested list(list(dict{}...))
    """
    for head in tab_ass.values():
        if table in head.keys():
            if isinstance(head[table], dict):
                return True
    return False

def id_gen(start):
    """Generator that yields series of integers starting at 'start'.

    Args:
        - start (int) : start value
    """
    counter = 1
    while True:
        yield counter + start
        counter = counter + 1

def adjust_keys(meas_dict):
    """JSON/YAML can't parse datetime onjects and None (python) or Null (Java)
    type values. This must be done manually.
    """
    for _, table_data in meas_dict.items():
        if isinstance(table_data, dict):
            table_data = conv_null_date(table_data)
        elif isinstance(table_data, list):
            for data_item in table_data:
                data_item = conv_null_date(data_item)
    return meas_dict

def conv_null_date(data_item):
    """Dates need to be converted to datetime and 'NULL' to 'None'. 'None' will
    be interpreted by sqlalchemy as 'NULL' while the uploading process.
    """
    if isinstance(data_item, list):
        for dic in data_item:
            for key, val in dic.items():
                date = string_to_datetime(val)
                if date is not False:
                    dic[key] = date
                elif val == "NULL":
                    dic[key] = None
    elif isinstance(data_item, dict):
        for key, val in data_item.items():
            date = string_to_datetime(val)
            if date is not False:
                data_item[key] = date
            elif val == "NULL":
                data_item[key] = None
    return data_item


def key_pop(dic, key, val):
    """Changes key name while keeping the old value. If value is not existing
    then a new key value pair is added to dict.
    """
    if val in dic.keys():
        dic[key] = dic.pop(val)
    else:
        dic.update({key : val})
    return dic


def convert_keys(meas_dict, conv_dict):
    """Convert key names so that they match the keys of a certain DB table.
    This information is provided by the 'key assignment' specifications
    in the cfg file.

    Args:
        - dic (dict)      : dict{ {table name : dict{ ... } },  ...}
        - meas_type (str) : type of measurement
    Returns:
        Converted dict in equal format.
    """
    for table_name, table_conv in conv_dict.items():    #pylint: disable = R1702
        for key, val in table_conv.items():
            if isinstance(meas_dict[table_name], dict):
                meas_dict[table_name] = key_pop(meas_dict[table_name],
                                                key, val)

            elif isinstance(meas_dict[table_name], list):
                for table_data in meas_dict[table_name]:
                    if isinstance(table_data, dict):
                        table_data = key_pop(table_data, key, val)
                    # highest level of allowed data nesting
                    elif isinstance(table_data, list):
                        for dic in table_data:
                            dic = key_pop(dic, key, val)
    return meas_dict

def compare_dicts(meas_dict, ass_dict):
    """Compares 'table assignment' dict with data dict and sorts the key/values
    with respect to the DB tables they relate to.
    """
    new_meas_dict = {}
    # assign header items to DB table
    for table, table_items in ass_dict[HEADER].items():
        temp_dict = {}
        for table_item in table_items:
            if table_item in meas_dict[HEADER].keys():
                temp_dict[table_item] = meas_dict[HEADER][table_item]
        new_meas_dict[table] = temp_dict
    meas_dict.pop(HEADER)

    # assign data items to DB table
    for head in DATA_HEADER:
        for table, table_item in ass_dict[head].items():
            new_meas_dict[table] = data_assignment(table_item, meas_dict[head])
    return new_meas_dict

def data_assignment(ass_item, data_item):
    """sorts and assignes key/values according to the DB table they will be
    uploaded into. Optional keys are emphazised by a '*' in the cfg file.
    """
    new_meas_list = []
    if isinstance(ass_item, list):
        for dic in data_item:
            temp_dict = {}
            for list_item in ass_item:
                try:
                    temp_dict[list_item] = dic[list_item]
                except KeyError:
                    if list_item.replace("*", "") in dic.keys():
                        temp_dict[list_item.replace("*", "")] \
                        = dic[list_item.replace("*", "")]
                    elif list_item.replace("*", "") not in dic.keys():
                        pass
                    else:
                        raise KeyError("Unkown key stated in 'table "
                                       "assignment' paragraph...")
            new_meas_list.append(temp_dict)
    elif isinstance(ass_item, dict):
        subdict_name = list(ass_item.keys())[0].replace("*", "")
        new_meas_list = get_nested_data(data_item, subdict_name)
    return new_meas_list


def get_nested_data(dict_list, name):
    """Returns nested items from a list of dicts. If there are no nested items
    then a empty list is returned.
    """
    new_list = []
    for dic in dict_list:
        for key in dic.keys():
            if key == name:
                new_list.append(dic[key])
    return new_list

def string_to_datetime(string):
    """Converts strings of format 'dd.mm.yyyy h:min:sec' to datetime object.
    """
    try:
        datetime_obj = datetime.datetime.strptime(string, "%d.%m.%Y %X")
        return datetime_obj
    except ValueError:
        try:
            datetime_obj = datetime.datetime.strptime(string, "%Y-%m-%d %X")
            return datetime_obj
        except (ValueError, TypeError):
            return False

def insert_default_paras(meas_data, conv_dict):
    """Check if keys of DB table are missing and insert default key/values
    if that is the case. These parameters are given by the 'key assignment'
    paragraph in DB cfg file.
    """
    for table, conv_values in conv_dict.items():
        for key, val in conv_values.items():
            if isinstance(meas_data[table], dict):
                if key not in meas_data[table].keys():
                    meas_data[table][key] = val
            elif isinstance(meas_data[table], dict):
                for dic in meas_data[table]:
                    if key not in dic.keys():
                        dic[key] = val

    return meas_data

# if __name__ == '__main__':
#     DB = DBHandler()
    # DB = DBHandler(os.path.join(os.getcwd(),
    #                             "models\\pytester\\Pytester_DB_new.cfg"))
    # sensor = yaml.load(open("..\\test\\test_sensor.yml"))
    # data = {'header': {'measurement': 'IV', 'name': 'Andreas_1',
    #                    'project': 'DBHandler', 'operator': 'Metzler',
    #                    'date': '29.05.2018 15:00:00'},
    #         'data': [{'id': 0, 'High_Voltage_set': '0',
    #                   'Amperemeter_get': -7.11469e-08},
    #                  {'id': 1, 'High_Voltage_set': '1',
    #                   'Amperemeter_get': 9.042474e-07},
    #                  {'id': 2, 'High_Voltage_set': '2',
    #                   'Amperemeter_get': 1.898752e-06},
    #                  {'id': 3, 'High_Voltage_set': '3',
    #                   'Amperemeter_get': 2.874317e-06}]}
    # DB.upload_data(data, "print only")
    # print(DB.get_dict("db_info_test"))
