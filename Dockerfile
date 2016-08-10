FROM php:7.0-apache

RUN DEBIAN_FRONTEND=noninteractive \
    apt-get update && \
    apt-get install -y unzip

RUN a2enmod rewrite

RUN sed -i 's#DocumentRoot /var/www/html#DocumentRoot /var/www/html/web#' /etc/apache2/sites-available/000-default.conf

RUN curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer

COPY . /var/www/html/

COPY config.php.docker /var/www/html/config.php

RUN chown -R www-data /var/www/html/var

RUN composer install --prefer-dist --no-dev --no-interaction
