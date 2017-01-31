import sqlalchemy
import collections
import operator
import string

class getResults():

    def __init__(self, htype=None, model=None, experimentSN=None, 
                 hardwareLabel=None, travelerName=None, stepName=None, 
                 schemaName=None, valueName=None, sortBy=None, 
                 sortByType='int', runLabel=None, stepStatus='success', 
                 travelerStatus=None,dbConnectFile='db_connect.txt'):
        self.htype = htype
        self.model = model
        self.experimentSN = experimentSN
        self.hardwareLabel = hardwareLabel
        self.travelerName = travelerName
        self.schemaName = schemaName
        self.valueName = valueName
        self.sortBy = sortBy
        self.sortByType = sortByType
        self.runLabel = runLabel
        self.stepStatus = stepStatus
        self.travelerStatus = travelerStatus
        self.dbConnectFile = dbConnectFile

    def setParams(self, htype=None, model=None, experimentSN=None, 
                 hardwareLabel=None, travelerName=None, stepName=None, 
                 schemaName=None, valueName=None, sortBy=None, 
                 sortByType=None, runLabel=None, stepStatus=None, 
                 travelerStatus=None,dbConnectFile=None):
        if htype is not None: self.htype = htype
        if model is not None: self.model = model
        if experimentSN is not None: self.experimentSN = experimentSN
        if hardwareLabel is not None: self.hardwareLabel = hardwareLabel
        if travelerName is not None: self.travelerName = travelerName
        if schemaName is not None: self.schemaName = schemaName
        if valueName is not None: self.valueName = valueName
        if sortBy is not None: self.sortBy = sortBy
        if sortByType is not None: self.sortByType = sortByType
        if runLabel is not None: self.runLabel = runLabel
        if stepStatus is not None: self.stepStatus = stepStatus
        if travelerStatus is not None: self.travelerStatus = travelerStatus
        if dbConnectFile is not None: self.dbConnectFile = dbConnectFile

        # NOTE:  For first attempt, only use
        #     htype, dbConnectFile, schemaName
        #     travelerName if present
        #     and, if present, model and experimentSN
        #
        #     stepStatus has default value of 'success'. Does anything
        #     else ever make sense?
        #     stepName doesn't buy us much; might not implement ever

    def connectDB(self):

        kwds = {}
        try:
            with open(self.dbConnectFile) as f:
                for line in f:
                    (key, val) = line.split()
                    kwds[key] = val
        except IOError:
            raise IOError, "Unable to open db connect file" + self.dbConnectFile

        # Create a new mysql connection object.
        db_url = sqlalchemy.engine.url.URL('mysql+mysqldb', **kwds)
        engine = sqlalchemy.create_engine(db_url)
        mysql_connection = engine.raw_connection()

        print 'connected to host' , kwds['host']

        # Appears not to be used for anything
        #cursor = mysql_connection.cursor()

        return engine

    def getResultsJH(self,engine):
        self.verifyParameters()

	# Form list of hardware ids for components of interest
        hids = []
        hids_str = []
        hidQuery = "select H2.id as hid2 from Hardware H2 join HardwareType HT on H2.hardwareTypeId=HT.id where HT.name='" + self.htype + "'"
        if self.experimentSN is not None:
            hidQuery += " and H2.lsstId='" + self.experimentSN + "'"

        elif self.model is not None:    
            hidQuery += "and H2.model='" + self.model + "'"

        # To support hardware label arg, add extra condition to where clause
        # but not for this first attempt

        print "hardware query is: \n"
        print hidQuery, "\n"

        # Retrieve list of all rootActivityId's which may be relevant
        # (correct process name; run on a component we care about)
        rootsQuery = "select A.id as Aid, H.id as Hid from Hardware H join Activity A on H.id=A.hardwareId join Process P on A.processId=P.id where H.id in (" + hidQuery + ") and A.id=A.rootActivityId and P.name='" + self.travelerName + "' order by H.id asc, A.id desc"

        print "Query to find traveler root ids of interest\n"
        print rootsQuery, "\n"
        result = engine.execute(rootsQuery)

        raiList = []
        for row in result:
            print "hid=",row['Hid']," rootId=",row['Aid']
            raiList.append(str(row['Aid']))
        if len(raiList) == 0:
            print "No results meeting criteria"
            exit(0)
        
        # Form list of interesting rootId's
        raiString = "('" + string.join(raiList, "','") + "')"
        print "raiString: ", raiString, "\n"
            

        rquery = "select FRH.name as FRHname,FRH.value as FRHvalue,FRH.schemaInstance as FRHsI,A.id as aid,A.hardwareId as hid,ASH.activityStatusId as actStatus from FloatResultHarnessed FRH join Activity A on FRH.activityId=A.id join ActivityStatusHistory ASH on A.id=ASH.activityId where FRH.schemaName='"
        rquery += self.schemaName
        rquery += "' and A.rootActivityId in " + raiString + " and ASH.activityStatusId='1' order by A.hardwareId asc, A.rootActivityId desc, FRHsI,FRHname"

        print "Monster query:\n"
        print rquery

        rresult = engine.execute(rquery)
        #print "Found ",len(rresult), " rows"

        for row in rresult:
          print "Hid: ",row['hid'], " Aid: ",row['aid']," FRH instance: ", row['FRHsI'], "FRHname: ",row['FRHname']," FRHvalue: ",row['FRHvalue'], " Act status: ", row['actStatus']


    def verifyParameters(self):
        if self.htype is None:
            raise KeyError,'Missing value for "htype"'
        if self.schemaName is None:
            raise KeyError, 'Missing value for "schemaName"'

 
if __name__ == "__main__":
    
    schemaName = 'read_noise'
    valueName = 'read_noise'
    htype = 'ITL-CCD'
    travelerName = 'SR-EOT-1'

    title = valueName + '-' + travelerName + '-' + htype

    #eT = getResults(schemaName=schemaName, valueName=valueName, htype=htype, travelerName=travelerName, experimentSN='ITL-3800C-021', dbConnectFile='/u/ey/jrb/et_prod_query.txt')

    eT = getResults(schemaName=schemaName, valueName=valueName, htype=htype, travelerName=travelerName,  model='3800C', dbConnectFile='/u/ey/jrb/et_prod_query.txt')

    engine = eT.connectDB()

    ccd  = eT.getResultsJH(engine)


