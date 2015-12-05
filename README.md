# Transport API

[![Build Status](https://secure.travis-ci.org/OpendataCH/Transport.png?branch=master)](http://travis-ci.org/OpendataCH/Transport)

The Transport API allows interested developers to build their own applications using public timetable data, whether they're on the web, the desktop or mobile devices.

Feel free to fork this project implement your own ideas or send pull requests.

## Installation

You can install the Transport API on your own server, however we recommend the usage of [transport.opendata.ch](http://transport.opendata.ch/).

```
$ git clone git://github.com/OpendataCH/Transport.git transport
$ cd transport
$ composer install
```

Also make sure, the directory ```transport/var/``` is writable.

If you cloned the repository inside your document root, the API is now accessible at [http://localhost/transport/web/api.php/v1/](http://localhost/transport/web/api.php/v1/locations?query=Basel). However we recommend setting the document root to ```transport/web/``` and using the provided ```.htaccess``` to route API requests to ```api.php```.

Or you can start it with the php's built-in webserver (not recommended for a production setup, but the easy way to get started locally)

```
php -S localhost:8000
```

And then access it with [http://localhost:8000/web/api.php](http://localhost:8000/web/api.php)

### Configuration

To define your own configuration for the API copy the file ```config.php.sample``` to ```config.php``` and override the variables you want to change.

### Statistics

You can get some basic statistics for the API by configuring a Redis server in your configuration (```$redis```) and have a look at [http://localhost/transport/web/stats.php](http://localhost/transport/web/stats.php).

## Development

XSD for the XML Fahrplan API is available here: https://gist.github.com/2309851
