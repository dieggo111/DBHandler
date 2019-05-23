# pylint: disable=C0326, C0103, R0903, C0111
from sqlalchemy import BigInteger, Column, Integer, String, Float, DateTime
from sqlalchemy import Date, Enum, Boolean, LargeBinary #pylint: disable=W0611
from ..meta import BASE #pylint: disable=E0402

class etl_tct_run(BASE):

    __tablename__ = "etl_tct_run"

    runid               = Column(Integer, primary_key=True)
    temperature         = Column(Float)
    bias_voltage        = Column(Float)
    scope               = Column(String)
    operator            = Column(Integer)
    humidity            = Column(Float)
    comment             = Column(String)
    rawdata_localpath   = Column(String)
    sensorid            = Column(Integer)
    bias_current        = Column(Float)
    time                = Column(DateTime)
    measurement_type    = Column(Integer)
    flag                = Column(Enum("good", "bad", "meas", "valid"))
    signal_source       = Column(Enum("sr90", "laser"))
    board               = Column(Integer)
    board_channel       = Column(Integer)
    reference           = Column(String)


class etl_tct_pulse(BASE):

    __tablename__ = "etl_tct_pulse"

    pulseid         = Column(BigInteger, primary_key=True)
    eventid         = Column(Integer)
    runid           = Column(Integer)
    risetime        = Column(Float)
    charge          = Column(Float)
    signalheight    = Column(Float)
    slope           = Column(Float)
    pulselength     = Column(Float)
    noise           = Column(Float)
    scope_channel   = Column(Integer)
    pulse_source    = Column(Enum("reference", "dut"))

class etl_tct_cfd_time(BASE):

    __tablename__ = "etl_tct_cfd_time"

    cfdid                   = Column(BigInteger, primary_key=True)
    pulseid                 = Column(BigInteger)
    fraction                = Column(Integer)
    time                    = Column(Float)
