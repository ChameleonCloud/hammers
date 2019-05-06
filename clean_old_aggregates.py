import keystoneauth1
import datetime
from keystoneauth1.identity import v3
from keystoneauth1 import loading
from keystoneauth1 import session
from novaclient import client as nova_client
from blazarclient import client as blazar_client

def main():

    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(auth_url='http://REDACTED:35357',
    username='admin',
    password='REDACTED',
    project_id='REDACTED',
    user_domain_id ='default')

    sess = session.Session(auth=auth)

    nova = nova_client.Client(version='2', region_name='CHI@TACC', session=sess)
    blazar = blazar_client.Client(1, session=sess, service_type='reservation', region_name='CHI@TACC')

    term_leases=[]
    agglist=[]
    aggdetails=[]
    aggnames=[]
    exp_aggs=[]
    agg_host=[]

    # Find leases with end date before current time
    leases=blazar.lease.list()

    time=datetime.datetime.now()
    for x in leases:
        lease_time=datetime.datetime.strptime(x['end_date'], '%Y-%m-%dT%H:%M:%S.%f')
        if lease_time < time:
            print("lease ending {} has ended. Time {}".format(lease_time,time))
            term_leases.append(x['reservations'][0]['id'])

    # Find aggregates matching ended leases
    aggregates=nova.aggregates.list()

    for agg in aggregates:
        ags=str(agg)
        agglist.append(ags[12:17])

    for x in agglist:
        aggdetails.append(nova.aggregates.get_details(x).__dict__)

    for x in aggdetails:
        aggnames.append({x['id'] : x['name']})

    for term_lease_item in term_leases:
        try:
            match=next(x for x in aggnames if term_lease_item == x.values()[0])
            #print("{}".format(match.keys()[0]))
            exp_aggs.append(match.keys()[0])
        except StopIteration:
            pass

    for agg in exp_aggs:
        agg_host.append({agg : nova.aggregates.get(agg).hosts})

    for x in agg_host:
        if x.values()!=[[]]:
            for host in x.values()[0]:
                print("Deleting host {} from aggregate {}".format(host, x.keys()))

if __name__ == "__main__":
    main()
