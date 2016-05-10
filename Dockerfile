FROM php:7.0-apache

RUN a2enmod rewrite

RUN sed -i 's#DocumentRoot /var/www/html#DocumentRoot /var/www/html/web#' /etc/apache2/apache2.conf

RUN curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer

COPY . /var/www/html/

COPY config.php.docker /var/www/html/config.php

RUN composer install
