FROM php:8.3-apache

RUN DEBIAN_FRONTEND=noninteractive \
    apt-get update && \
    apt-get install -y unzip

# Use the default production configuration
RUN mv "$PHP_INI_DIR/php.ini-production" "$PHP_INI_DIR/php.ini"

RUN a2enmod rewrite

RUN sed -i 's#DocumentRoot /var/www/html#DocumentRoot /var/www/html/web#' /etc/apache2/sites-available/000-default.conf

RUN curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer

COPY . /var/www/html/

COPY config.php.docker /var/www/html/config.php

RUN chown -R www-data /var/www/html/var

RUN composer install --prefer-dist --no-dev --no-interaction
