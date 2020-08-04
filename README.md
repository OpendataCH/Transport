> **The backend of the Transport API changed on 31 July 2017.** [Read more on opendata.ch](https://opendata.ch/2017/06/search-ch-rettet-transport-opendata-ch/).

# Transport API

![Build](https://github.com/OpendataCH/Transport/workflows/Build/badge.svg)

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

Or you can start it with the PHP's built-in webserver (not recommended for a production setup, but the easy way to get started locally)

```
php -S localhost:8000
```

And then access it with [http://localhost:8000/web/api.php](http://localhost:8000/web/api.php)

### Configuration

To define your own configuration for the API copy the file ```config.php.sample``` to ```config.php``` and override the variables you want to change.

### Statistics

You can get some basic statistics for the API by configuring a Redis server in your configuration (```$redis```) and have a look at [http://localhost/transport/web/stats.php](http://localhost/transport/web/stats.php).

## Development

XSD for the XML Fahrplan API is available here: [hafasXMLInterface.xsd](hafasXMLInterface.xsd)

## Troubleshooting

### Missing package php-xml

If you're running Ubuntu and `composer install` produces the error message

    Your requirements could not be resolved to an installable set of packages.

you can try to install the package `php-xml` using the command

    sudo apt install php-xml
