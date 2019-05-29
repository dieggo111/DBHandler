"""Default SQLite metadata"""
# pylint: disable=C0111, C0103, R0903, R0201, E0402
from sqlalchemy import Boolean, Column, Integer, String, Float, DateTime
from sqlalchemy import Date, Enum
from ..meta import BASE

class db_info(BASE):

    __tablename__ = "info"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    project = Column(String)
    manufacturer = Column(String)
    Class = Column(String)
    sensortype = Column(String)
    specification = Column(String)
    thickness = Column(Float)
    width = Column(Float)
    length = Column(Float)
    strips = Column(Float)
    pitch = Column(Float)
    coupling = Column(Enum("AC", "DC"))
    date = Column(Date)
    contact = Column(String)
    institute = Column(String)
    status = Column(String)
    backup_name = Column(String)
    F_p_aim_n_cm2 = Column(Float)
    F_n_aim_n_cm2 = Column(Float)
    parent = Column(String)
    defect = Column(Integer)

class db_probe(BASE):

    __tablename__ = "probe"

    probeid = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(Integer)
    paraX = Column(String)
    paraY = Column(String)
    paraZ = Column(String)
    date = Column(DateTime)
    operator = Column(String)
    temperature = Column(Float)
    flag = Column(String)
    guardring = Column(Boolean)

class db_probe_data(BASE):

    __tablename__ = "probe_data"

    # probe_uid = Column(BigInteger().with_variant(Integer, "sqlite"),
    #                    primary_key=True, autoincrement=True)
    probe_uid = Column(Integer, primary_key=True, autoincrement=True)
    probeid = Column(Integer)
    datax = Column(Float)
    datay = Column(Float)
    dataz = Column(Float)
    temperature = Column(Float)
    RH = Column(Float)
    errory = Column(Float)
    time = Column(DateTime)
    bias_current = Column(Float)

class db_probe_subdata(BASE):

    __tablename__ = "probe_subdata"

    subdataid = Column(Integer, primary_key=True, autoincrement=True)
    probe_uid = Column(Integer)
    dataX = Column(Float)
    dataY = Column(Float)
