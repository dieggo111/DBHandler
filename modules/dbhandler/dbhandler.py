#pylint: disable=R0912
"DBHandler module"
import logging
import os
import datetime
import inspect
import copy
from pydoc import locate
import yaml
import sqlalchemy
from sqlalchemy.orm import sessionmaker
try:
    from .models import meta
except (ModuleNotFoundError, ImportError):
    from models import meta
from DBHandler.core import Module
# absolute path of dbhandler module
MODPATH = os.path.dirname(\
    os.path.abspath(inspect.getfile(inspect.currentframe())))
# MODPATH = os.getcwd()
DEFAULT_MODEL = os.path.join("models", "default", "default.yml")
# define header names of incomming data
HEADER = "header"        # header name is mendatory
DATA_HEADER = ["data"]   # at least one data_header is mendatory

class DBHandler(Module): #pylint: disable=R0902
    """Database handling

    Methods:
        - load_cred:        loads credentials to access a mySQL DB
        - load_cfg:         loads cfg file with info about DB and its tables
        - get_dict:         returns table row
        - add_item:         adds dict to DB table
        - get_table_keys:   gets list of all DB table keys
        - get_values:       returns all values of key in DB table
        - update_all_values:changes certain value of all items in table
        - update_value:     changes a certain value of certain items
        - check_for_value:  checks if value is in DB table or not
        - untangle_data:    untangles a data container and adjusts data so that
                            data can be added to respective table
        - upload_data:      uploads data container to DB
        - get_dbt:          returns DBTable object
        - get_session:      returns the session object
    """
    _type = 'dbhandler'

    def __init__(self, *args, **kwargs):
        """The initialization is mostly done by the module base class
        (setting up logger, connecting to backend, etc). If the DBHandler is
        used outside of the MC framework:
            - pass the location of the DB cfg file as an argument
            - pass 'default' to run with the default local sqlite DB
              (also used for unittest)

        Expected structure of DB credential file:
            - cred = {"host"      : "...",
			          "database"  : "...",
			          "user"      : "...",
			          "passwd"    : "..."}
        """
        self.cfg_path = ""
        for arg in args:
            if os.path.isfile(arg) or arg == "default":
                self.cfg_path = arg
        super().__init__(*args, **kwargs)

    def _apply_config(self):
        """Is called by the base class during initialization. Loads
        credentials, DB structure and name of DB map from cfg file,
        creates DB session. Creates DBTable object to get table names of DB
        from cfg file, imports table classes and gets name of primary keys.
        """
        if self.cfg_path == "":
            # deprecated?
            if "modelpath" in self.config['dbhandler'].keys():
                db_cfg = self.load_cfg(\
                        self.config['dbhandler']["modelpath"])
            else:
                model = self.config['dbhandler'].get("model", "default")
                self.log.debug("Load model '%s'", model)
                db_cfg = self.load_cfg(os.path.join(MODPATH,\
                                'models/{0}/{0}.yml'.format(model)))
        else:
            db_cfg = self.load_cfg(self.cfg_path)
        self.dbt = DBTable(map_file=db_cfg["map"], #pylint: disable=W0201
                           table_dict=db_cfg["tables"],
                           cr_dict=db_cfg["cross-reference"])

        if db_cfg["engine"] == "sqlite":
            engine = sqlalchemy.create_engine("sqlite:///mySQlite.db")
            meta.BASE.metadata.create_all(engine, checkfirst=True)
            session = sessionmaker(bind=engine)
            self.session = session() #pylint: disable=W0201
        elif db_cfg["engine"] == "mysql+mysqlconnector":
            # if absolute path is given by cfg file
            if os.path.isfile(db_cfg["credentials"]):
                cred = self.load_cred(db_cfg["credentials"])
            # check dedicated credentials folder for credentials file
            elif os.path.isfile(os.path.join(
                    MODPATH, "credentials", db_cfg["credentials"])):
                cred = self.load_cred(os.path.join(
                    MODPATH, "credentials", db_cfg["credentials"]))
            # check working directory for credentials file
            elif os.path.isfile(
                    os.path.join(os.getcwd(), db_cfg["credentials"])):
                cred = self.load_cred(os.path.join(os.getcwd(),
                                                   db_cfg["credentials"]))
            else:
                raise FileNotFoundError("Couldn't find or read credentials...")

            engine = sqlalchemy.create_engine(db_cfg["engine"]
                                              + "://"
                                              + cred["user"] + ":"
                                              + cred["passwd"] + "@"
                                              + cred["host"] + ":"
                                              + "3306" + "/"
                                              + cred["database"])
            session = sessionmaker(bind=engine)
            self.session = session() #pylint: disable=W0201
        else:
            self.log.warning("Unkown engine in DB cfg...")

        self.table_ass = db_cfg["table assignment"] #pylint: disable=W0201
        self.meas_tk = db_cfg["measurement type key"] #pylint: disable=W0201
        self.cross_ref = db_cfg["cross-reference"] #pylint: disable=W0201

        if self.dbt.all_names() == []:
            self.log.warning("Import of table classes failed...")
        else:
            self.dbt.set_session(self.session)
            self.log.info("Connection to database established...")
            self.log.info("Imported table classes: %s",
                          ", ".join(self.dbt.all_names()))

    def load_cred(self, arg):
        """Handles the import of credentials"""
        cred = yaml.load(open(arg, "rb"))
        self.log.debug("Loaded credentials from %s", arg)
        return cred

    def load_cfg(self, db_cfg):
        """Handles the import of cfg dict.
            - Load default SQLlite model if db_cfg is'default'
            - return db_cfg as it is, if not a path
        """
        try:
            if isinstance(db_cfg, dict):
                return db_cfg
            if db_cfg == "default":
                db_cfg = os.path.join(MODPATH, DEFAULT_MODEL)
            with open(db_cfg, "r") as cfg:
                db_cfg = yaml.load(cfg)
                cfg.close()
            return db_cfg
        except TypeError:
            self.log.error("Failed to load DB resources. Unexpected type(arg)")
            raise ImportError
        except FileNotFoundError:
            self.log.error("Failed to load DB resources...")
            raise ImportError

    def update_value(self, new_val, prim_key_lst, #pylint: disable=R0913
                     prim_key="probeid", update_key="id", table="db_probe"):
        """Update values of certain key of items.
        Args:
            - new_val: the new value you want to update for
            - prim_key_lst (list): list of primary keys to identify target
                                   items you want to update
            - prim_key (str): the name of the table's primary key
            - update_key (str): the name of the key you want to update
            - table (str/DBT object): the table that contains the items you
                                      want to update
        """
        if isinstance(table, str):
            table = self.dbt.obj(table)
        if prim_key == self.dbt.primkey(table):
            for _pk in prim_key_lst:
                self.session.query(table).filter(
                    getattr(table, prim_key) == _pk).\
                    update({getattr(table, update_key) : new_val})
                self.log.info("Changed '%s' of '%s' to %s", update_key,
                              str(_pk), str(new_val))
        else:
            self.log.error("Argument 'prim_key' does not state the table's "
                           "primary key. The items you plan to update can not "
                           "be identified.")

    def search_table(self, table, **kwargs):
        """Basic search operation: search for key-value in DB table and filter
        your data by passing keyword arguments. You can add '%' in a kwarg
        for a wildcard search. One wildcard allowed at a time.

        Args:
            - table (sqlalchemy.ext.declarative class/str) : table object/name
            - **kwargs : e.g. name="...", project="..."
        """
        if isinstance(table, str):
            table = self.dbt.obj(table)
        wildcard = {}
        # check vor wildcards in kwargs
        for key, val in kwargs.items():
            try:
                if "%" in val:
                    wildcard[key] = val.replace("%", "")
            except TypeError:
                pass
        if len(wildcard) > 1:
            self.log.warning("Only 1 wildcard per search allowed!")
            return None
        # use wildcard + rest of kwargs to filter DB data
        if wildcard != {}:
            wc_key = list(wildcard.keys())[0]
            kwargs.pop(wc_key)
            data = self.session.query(table).filter(\
                   getattr(table, wc_key).contains(\
                   wildcard[wc_key])).filter_by(**kwargs)
            return data
        data = self.session.query(table).filter_by(**kwargs)
        return data


    def get_dict(self, table, pk_value=None):
        """Returns dict with all key:value-pairs from table. To print a
        specific row pass its primary key value. Default is all rows of table.

        Args:
            - table (sqlalchemy.ext.declarative class/str) : table object/name
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

        except Exception as err: # pylint: disable=W0703
            print(err)
            # if "Session.rollback()" in str(err):
            #     pass
            # else:
            #     self.log.error("Item couldn't be added to DB...")
            #     self.log.debug(err)
            #     self.log.debug(item)

    def update_all_values(self, table, attr, old_value, new_value):
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

    def get_table_info(self, table):
        """Retrieve a list of all keys of a DB table.

        Args:
            - table (sqlalchemy.ext.declarative class or str) : table object

        Returns:
            Table keys as list of strings.
        """
        table_info = []
        if isinstance(table, str):
            table = self.dbt.obj(table)

        inst = sqlalchemy.inspect(table)
        try:
            table_info = [(c_attr.key, c_attr.type.python_type) \
                         for c_attr in inst.mapper.columns]
        except NotImplementedError:
            self.log.warning("Type of DB column can not be translated "
                             "into python type.")
        return table_info

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

    def check_for_value(self, table, **kwargs):
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
        check = list(self.session.query(table).filter_by(**kwargs))
        if check == []:
            return False
        return True

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
        self.log.debug("Recieved data container %s", meas_dict)
        try:
            new_meas_dict = sort_keys_by_tables(meas_dict,
                                                self.table_ass[meas_type])
        except Exception as err_msg:#pylint: disable=W0703
            self.log.warning("Untangling and sorting data was not succesfull")
            self.log.warning(err_msg)
            new_meas_dict = {}
        return new_meas_dict

    def check_data_types(self, meas_dict): # pylint: disable=too-many-branches
        """Loops through sorted data dictionary in order to check and
        convert data types.
        """
        station = meas_dict.get('db_probe', dict).get('station', None)
        if isinstance(station, str):
            if station == "probe_left":
                station = 1
            elif station == "probe_right":
                station = 2
            meas_dict['db_probe']['station'] = station

        for table, data in meas_dict.items():
            info = self.get_table_info(table)
            if isinstance(data, dict):
                for db_key, db_type in info:
                    try:
                        meas_dict[table][db_key] = adjust_types(db_type, \
                                            meas_dict[table][db_key])
                    except ValueError:
                        self.log.error("Error while converting key <%s> from "\
                           "table <%s> to type <%s>", db_key, table, db_type)
                        raise ValueError
                    except TypeError:
                        self.log.error("Error while converting key <%s> from "\
                           "table <%s> to type <%s>", db_key, table, db_type)
                        raise TypeError
                    except KeyError:
                        pass
            if isinstance(data, list):
                converted_lst = []
                for dic in data:
                    for db_key, db_type in info:
                        try:
                            dic[db_key] = adjust_types(db_type, dic[db_key])
                        except ValueError:
                            raise ValueError
                        except KeyError:
                            pass
                    converted_lst.append(dic)
                meas_dict[table] = converted_lst
        return meas_dict

    def upload_data(self, data, option="upload only"):  # pylint: disable=R0912, R1710
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
        if not isinstance(data, dict):
            self.log.warning("Recieved data container is expected to "
                             "be of type dict.")
            return False
        # check data and sort it by DB table
        meas_data = self.untangle_data(data)
        if meas_data == {}:
            self.log.warning("Upload request rejected")
            return False
        # add missing table cross-reference key/values
        meas_data = self.add_cross_ref(meas_data)
        # check value types and convert it if necessary
        try:
            meas_data = self.check_data_types(meas_data)
        except (TypeError, ValueError):
            self.log.warning("Can not convert data type")
            return False
        # add data:
        try: #pylint: disable=R1702
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
                return True
        except: #pylint: disable=W0702
            self.log.warning("Upload was not succesful...")
            return False

    def get_dbt(self):
        """Returns DBTable object.
        """
        return self.dbt

    def get_session(self):
        """Returns engine object"""
        return self.session

    def get_table_ass(self):
        return self.table_ass


#########################################################
##################### DBTable Class #####################
#########################################################

class DBTable():
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
            return {info["para"]: val[0]}

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

def sort_keys_by_tables(meas_dict, ass_dict):
    """Sorts data by DB tables. Changes key names from data container into
    key names that are expected from DB, checks for incomplete data containers
    and adds constants (according to config file).

    Args:
        - meas_dict (dict): raw unsorted data container
        - ass_dict (dict): sort structure given by cfg file
    """
    new_meas_dict = copy.deepcopy(ass_dict)
    for table in ass_dict[HEADER].keys():
        for table_key, data_key in ass_dict[HEADER][table].items():
            new_meas_dict[HEADER][table][table_key] \
                    = return_data_val(meas_dict[HEADER], data_key)

    for data in DATA_HEADER:
        for table in ass_dict[data]:
            new_meas_dict[data][table] = []
            for data_dict in meas_dict[data]:
                temp_dict = copy.deepcopy(ass_dict[data][table])
                for table_key, data_key in ass_dict[data][table].items():
                    if isinstance(data_key, dict):
                        new_meas_dict[data][table] += \
                return_nested_data(data_dict, table_key, data_key)
                        temp_dict = None
                    else:
                        temp_dict[table_key] = return_data_val(data_dict,
                                                               data_key)
                if temp_dict is not None:
                    new_meas_dict[data][table].append(temp_dict)
    final_dict = {}
    final_dict.update(new_meas_dict.pop(HEADER))
    for data in DATA_HEADER:
        final_dict.update(new_meas_dict.pop(data))
    return final_dict

def return_nested_data(dic, key, val_dict):
    """Nested data is collected from dict, sorted according to val_dict
    (cfg file), bundled and then returned as a list.

    Args:
        - dic (dict): raw data dict which contains the nested data
        - key (dict key): its value contains the nested data
        - val_dict (dict): sort structure given by cfg file
    """
    lst = []
    for nested_dict in dic[key]:
        temp_dict = {}
        for nested_key, nested_val in val_dict.items():
            temp_dict.update({nested_key:
                              return_data_val(nested_dict, nested_val)})
        lst.append(temp_dict)
    return lst

def return_data_val(dic, data_key):
    """Returns the valus of a specific key. Checks if key is in dic and if it's
    a mandatory key (raises value if not present) or a DB constant.
    """
    if data_key not in dic.keys() and "*" not in data_key:
        raise ValueError("Incomplete dict: mandatory key {} not found.".format(
            data_key))
    if "*" in data_key:
        return data_key.replace("*", "")
    return dic[data_key]

def string_to_datetime(string):
    """Converts strings of central European format 'dd.mm.yyyy h:min:sec'
    or US format 'yyyy-mm-dd h:min:sec' to datetime object. Milliseconds are
    optional for US format.
    """
    if "." in string[:6]:
        datetime_obj = datetime.datetime.strptime(string, "%d.%m.%Y %X")
        return datetime_obj
    if "-" in string[:6]:
        try:
            datetime_obj = datetime.datetime.strptime(string, "%Y-%m-%d %X")
            return datetime_obj
        except ValueError:
            datetime_obj = datetime.datetime.strptime(string, "%Y-%m-%d %X.%f")
            return datetime_obj
    raise ValueError

def adjust_types(db_type, val):
    """Compares type of value with expected type in DB column and converts it
    if necessary.
    """
    if db_type == datetime.datetime:
        return string_to_datetime(val)
    if isinstance(val, db_type):
        return val
    if val in ["true", "True"]:
        return True
    if val in ["False", "false"]:
        return False
    return db_type(val)
