# Installation Process

## Objective:
Run a Grafana instance to provide a monitoring dashboard to a gluster cluster.

## Pre-requisites
### Monitoring host
- docker and docker-compose (for simplicity)
- grafana image (official latest 4.3 release from docker hub)
- graphite image (docker.io/abezhenar/graphite-centos7)
- the storage for the graphite database should be on SSD/flash if possible

### GlusterFS cluster machine
- python
- pip install graphitesend


## Installation Sequence
Install the monitoring endpoint first, and then setup the collect points on
each of the Gluster nodes.


## Setting Up the monitoring endpoint
On the monitoring host, perform the following steps;
1. Pull the required docker images (*listed above*)
2. we need to persist the grafana configuration db and settings, as well as the
graphite data.
```markdown
mkdir -p /opt/docker/grafana/etc
mkdir -p /opt/docker/grafana/data/plugins
mkdir -p /opt/docker/graphite
```
3. Download the additional status panel plugin
```markdown
cd /opt/docker/grafana/data/plugins
wget https://grafana.com/api/plugins/vonage-status-panel/versions/1.0.4/download
unzip download
rm -f download
```
4. Copy the seed .ini file for grafana to the containers etc directory, and reset
the permissions to be compatible with the containers
```markdown
cp etc/grafana/grafana.ini /opt/docker/grafana/etc
chown -R 104:107 /opt/docker/grafana
chown -R 997 /opt/docker/graphite
chmod g+w /opt/docker/graphite

```
5. Edit the `docker/docker-compose.yml` example (if necessary)
6. Run docker compose
```
cd docker/
docker-compose up -d
```
7. check that the containers are running and the endpoints are listening
7.1 Use ```docker ps```
7.2 use ```netstat``` and look for the following ports: 3000,80,2003,2004,7002

8. Add the graphite instance as a datasource to grafana
8.1 register the graphite instance to grafana as the default data source
```markdown
curl -u admin:admin -H "Content-Type: application/json" -X POST http://localhost:3000/api/datasources \
--data-binary @setup/add_datasource.json
```

## Configuration on Each Gluster Node
* You may need to update your SELINUX policy to allow the write_graphite plugin
to access outbound on port 2003. To test, simply disable SELINUX
* Install Gluster metrics library to enable tracking utilization, process and
  diskstats

    sudo pip install git+https://github.com/gluster/glustercli-python.git

* Run below command to start sending metrics to graphite server

```
$ python gmetrics.py
```

Graphite server and hostname can be configured using,

```
$ python gmetrics.py --graphite-server localhost --hostname local
```

## Configurations
To customize the gmetrics, create a config file and override the settings

        [settings]
        interval=10
        enabled_metrics=local_io,local_process
        prefix=gbench_testing
        group=perf_test_1

And call `gmetrics.py` using,

```
$ python gmetrics.py -c /root/gmetrics.conf --graphite-server localhost \
        --hostname local
```

Configuration change will be detected automatically by `gmetrics.py`, config
file can be edited as required.

Available options for `enabled_metrics` are

```
    "local_io",
    "local_utilization",
    "local_diskstats",
    "local_process"
```

## Known Issues
* After login to grafana, currently users have to setup the dashboard themself.
* (**TODO**) Update other known issues


## Credits

Setting up of docker images for graphite and grafana section in this README is taken over from [cephmetrics](https://github.com/ceph/cephmetrics).
