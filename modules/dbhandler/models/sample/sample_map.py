# pylint: disable=C0326, C0103, R0903, C0111, E0402
from sqlalchemy import BigInteger, Column, Integer, String, Float, DateTime
from sqlalchemy import Date, Enum, Boolean, LargeBinary
from ..meta import BASE

class db_info(BASE):

    __tablename__ = "info"

    id              = Column(Integer, primary_key=True)
    name            = Column(String)
    project         = Column(String)
    manufacturer    = Column(String)
    Class           = Column(String)
    sensortype      = Column(String)
    specification   = Column(String)
    thickness       = Column(Float)
    width           = Column(Float)
    length          = Column(Float)
    strips          = Column(Float)
    pitch           = Column(Float)
    coupling        = Column(Enum("AC","DC"))
    date            = Column(Date)
    contact         = Column(String)
    institute       = Column(String)
    status          = Column(String)
    backup_name     = Column(String)
    F_p_aim_n_cm2   = Column(Float)
    F_n_aim_n_cm2   = Column(Float)
    parent          = Column(String)
    defect          = Column(Integer)

class db_probe(BASE):

    __tablename__ = "probe"

    probeid         = Column(Integer, primary_key=True)
    id              = Column(Integer)
    paraX           = Column(String)
    paraY           = Column(String)
    paraZ           = Column(String)
    date            = Column(DateTime)
    operator        = Column(String)
    temperature     = Column(Float)
    RH              = Column(Float)
    station         = Column(Integer)
    frequency       = Column(Float)
    comment         = Column(String)
    flag            = Column(Enum("good", "bad", "meas", "valid"))
    cern_timestamp  = Column(Integer)
    guardring       = Column(Boolean)
    amplitude_LCR   = Column(Float)
    mode_LCR        = Column(Enum("parallel", "serial"))
    N_steps         = Column(Integer)
    starttime       = Column(DateTime)
    stoptime        = Column(DateTime)
    bias            = Column(Float)
    Vdep            = Column(Float)
    fitmode         = Column(Integer)
    annealing_id    = Column(Integer)
    irradiation_id  = Column(Integer)

class db_probe_data(BASE):

    __tablename__ = "probe_data"

    probeid         = Column(Integer)
    probe_uid       = Column(BigInteger, primary_key=True)
    datax           = Column(Float)
    datay           = Column(Float)
    dataz           = Column(Float)
    temperature     = Column(Float)
    RH              = Column(Float)
    errory          = Column(Float)
    time            = Column(DateTime)
    bias_current    = Column(Float)

class db_alibava(BASE):

    __tablename__ = "alibava"

    alibava_uid             = Column(Integer, primary_key=True)
    run                     = Column(Integer)
    id                      = Column(Integer)
    ped_run                 = Column(Integer)
    date                    = Column(DateTime)
    source                  = Column(String)
    voltage                 = Column(Float)
    current                 = Column(Float)
    temperature             = Column(Float)
    x_position              = Column(Float)
    y_position              = Column(Float)
    z_position              = Column(Float)
    signal                  = Column(Float)
    sigma_signal            = Column(Float)
    electron_sig            = Column(Float)
    signal_e_err            = Column(Float)
    trigger                 = Column(Integer)
    chi2_signal             = Column(Float)
    chi2_snr                = Column(Float)
    comment                 = Column(String)
    mpv_snr                 = Column(Float)
    sigma_snr               = Column(Float)
    mpv_signal              = Column(Float)
    mean_clustersize        = Column(Float)
    mean_clustersize_cut    = Column(Float)
    mean_clusternoise       = Column(Float)
    mean_commonmode         = Column(Float)
    sigma_commonmode        = Column(Float)
    strip_mosthits          = Column(Integer)
    lownoise_limit          = Column(Float)
    highnoise_limit         = Column(Float)
    timing_one_ns           = Column(Integer)
    timing_two_ns           = Column(Integer)
    operator                = Column(String)
    temperature_daughterboard = Column(Float)
    cern_timestamp          = Column(BigInteger)
    RH                      = Column(Float)
    median_noise_used_strips = Column(Float)
    clusters                = Column(Integer)
    station                 = Column(Integer)
    chip                    = Column(Integer)
    signal_e_syserror       = Column(Float)
    flag                    = Column(Enum("good", "bad", "meas", "valid"))
    fakehits                = Column(Float)
    SeedSig_MPV             = Column(Float)
    SeedSig_MPV_err         = Column(Float)
    SeedSig_chi2_ndf        = Column(Float)
    SeedSigENC_MPV          = Column(Float)
    SeedSigENC_MPV_err      = Column(Float)
    SeedSigENC_chi2_ndf     = Column(Float)
    Signal_chi2_ndf         = Column(Float)
    calib_run               = Column(Integer)
    gain                    = Column(Float)
    # pdf                     = Column(LargeBinary)
    last_analyzed           = Column(DateTime)
    ThresholdAt995          = Column(Float)
    annealing_id            = Column(Integer)
    irradiation_id          = Column(Integer)

class db_annealing(BASE):

    __tablename__ = "annealing"

    annealing_id            = Column(Integer, primary_key=True)
    id                      = Column(Integer)
    date                    = Column(DateTime)
    temperature             = Column(Float)
    time                    = Column(Float)
    equiv                   = Column(Float)
    operator                = Column(String)
    sum                     = Column(Float)

class db_irradiation(BASE):

    __tablename__ = "irradiation"

    uirrad_id           = Column(Integer,primary_key=True)
    id                  = Column(Integer)
    F_n_cm2             = Column(Float)
    particletype        = Column(Enum("n", "p", "pi", "x"))
    date                = Column(DateTime)
    starttime           = Column(DateTime)
    endtime             = Column(DateTime)
    beamcurrent_uA      = Column(Float)
    temperature         = Column(Float)
    F_measure           = Column(Float)
    F_aim_n_cm2         = Column(Float)
    stack               = Column(Integer)
    hardnessfactor      = Column(Float)
    operator            = Column(String)
    comment             = Column(String)
    location            = Column(String)
    n_scans             = Column(Integer)
    scan_lines          = Column(Integer)
    scan_speed_mm_s     = Column(Integer)
    scan_width_mm       = Column(Integer)
    groupname           = Column(String)
    F_sum               = Column(Float(50))
    particles           = Column(String)

class db_operator(BASE):
    __tablename__ = "define_operator"

    id                  = Column(Integer, primary_key=True)
    operator            = Column(String)
    fullname            = Column(String)
