SET NAMES utf8;
SET time_zone = '+00:00';
SET foreign_key_checks = 0;
SET sql_mode = 'NO_AUTO_VALUE_ON_ZERO';

SET NAMES utf8mb4;

DROP TABLE IF EXISTS `api_logs`;
CREATE TABLE `api_logs` (
  `log_id` int(11) NOT NULL AUTO_INCREMENT,
  `api_id` int(11) NOT NULL,
  `method` varchar(256) NOT NULL,
  `data` longtext DEFAULT NULL,
  `result` longtext DEFAULT NULL,
  `time` int(11) NOT NULL,
  PRIMARY KEY (`log_id`),
  KEY `api_id` (`api_id`),
  KEY `time` (`time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


DELIMITER ;;

CREATE TRIGGER `api_logs_success` AFTER INSERT ON `api_logs` FOR EACH ROW
BEGIN
  UPDATE `api_users`
  SET `success_call`=`success_call`+1, `last_use`=UNIX_TIMESTAMP()
  WHERE `id`=NEW.api_id LIMIT 1;
END;;

DELIMITER ;

DROP TABLE IF EXISTS `api_logs_failed`;
CREATE TABLE `api_logs_failed` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `api_id` int(11) NOT NULL,
  `method` varchar(256) NOT NULL,
  `data` longtext DEFAULT NULL,
  `result` longtext DEFAULT NULL,
  `time` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `api_id` (`api_id`),
  KEY `time` (`time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


DELIMITER ;;

CREATE TRIGGER `api_logs_failed_user` BEFORE INSERT ON `api_logs_failed` FOR EACH ROW
BEGIN
  UPDATE `api_users`
  SET `fail_call`=`fail_call`+1, `last_use`=UNIX_TIMESTAMP()
  WHERE `id`=NEW.api_id LIMIT 1;
END;;

DELIMITER ;

DROP TABLE IF EXISTS `api_users`;
CREATE TABLE `api_users` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `email` text NOT NULL,
  `api_key` text NOT NULL,
  `encrypt_key` text NOT NULL,
  `max_address` int(11) NOT NULL DEFAULT 10000,
  `max_batch_records` int(11) NOT NULL DEFAULT 100,
  `allowed_coin` text NOT NULL,
  `success_call` int(11) NOT NULL DEFAULT 0,
  `fail_call` int(11) NOT NULL DEFAULT 0,
  `last_use` int(11) DEFAULT NULL,
  `is_suspended` tinyint(4) NOT NULL DEFAULT 0,
  `remark` text DEFAULT NULL,
  `created` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `email` (`email`(768)),
  KEY `api_key` (`api_key`(768)),
  KEY `is_suspended` (`is_suspended`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


DROP TABLE IF EXISTS `coin_settings`;
CREATE TABLE `coin_settings` (
  `coin_id` int(11) NOT NULL AUTO_INCREMENT,
  `enable` tinyint(1) NOT NULL DEFAULT 1,
  `coin_name` varchar(32) NOT NULL,
  `type` enum('XMR','BCN','TRTL-API','TRTL-SERVICE','BTC') NOT NULL,
  `has_pos` tinyint(1) NOT NULL DEFAULT 0,
  `use_getinfo_btc` tinyint(1) NOT NULL DEFAULT 0,
  `decimal` tinyint(4) NOT NULL DEFAULT 0,
  `round_places` tinyint(4) NOT NULL DEFAULT 8,
  `daemon_address` text DEFAULT NULL,
  `wallet_address` text DEFAULT NULL,
  `header` varchar(512) DEFAULT NULL,
  `is_fee_per_byte` tinyint(4) NOT NULL DEFAULT 0,
  `mixin` tinyint(4) DEFAULT NULL,
  `main_address` varchar(256) DEFAULT NULL,
  `min_deposit` float NOT NULL DEFAULT 0,
  `min_withdraw` float NOT NULL DEFAULT 0,
  `max_withdraw` float NOT NULL DEFAULT 0,
  `min_transfer` float NOT NULL DEFAULT 0,
  `max_transfer` float NOT NULL DEFAULT 0,
  `fee_deposit` float NOT NULL DEFAULT 0,
  `fee_withdraw` float NOT NULL DEFAULT 0,
  `chain_height` int(11) NOT NULL DEFAULT 0,
  `chain_height_set_time` int(11) DEFAULT NULL,
  `confirmation_depth` tinyint(2) NOT NULL,
  `enable_deposit` tinyint(4) NOT NULL DEFAULT 1,
  `enable_withdraw` tinyint(4) NOT NULL DEFAULT 1,
  `enbale_transfer` tinyint(4) NOT NULL DEFAULT 1,
  `enable_create` tinyint(4) NOT NULL DEFAULT 1,
  PRIMARY KEY (`coin_id`),
  KEY `enable` (`enable`),
  KEY `coin_name` (`coin_name`),
  KEY `enable_deposit` (`enable_deposit`),
  KEY `enable_withdraw` (`enable_withdraw`),
  KEY `enable_create` (`enable_create`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


DROP TABLE IF EXISTS `deposits`;
CREATE TABLE `deposits` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `coin_name` varchar(16) NOT NULL,
  `api_id` int(11) NOT NULL,
  `depost_id` int(11) NOT NULL,
  `txid` varchar(256) NOT NULL,
  `address` varchar(256) DEFAULT NULL,
  `extra` varchar(64) DEFAULT NULL,
  `height` int(11) DEFAULT NULL,
  `blockhash` varchar(64) DEFAULT NULL,
  `amount` float NOT NULL,
  `time_insert` int(11) NOT NULL,
  `can_credit` enum('YES','NO') NOT NULL DEFAULT 'NO',
  `confirmations` int(11) DEFAULT NULL,
  `already_noted` tinyint(1) NOT NULL DEFAULT 0,
  `noted_time` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `txid_address` (`txid`,`address`),
  KEY `coin_name` (`coin_name`),
  KEY `api_id` (`api_id`),
  KEY `address` (`address`),
  KEY `time_insert` (`time_insert`),
  KEY `txid` (`txid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


DELIMITER ;;

CREATE TRIGGER `deposits_to_address` AFTER UPDATE ON `deposits` FOR EACH ROW
BEGIN
  IF (OLD.can_credit<> NEW.can_credit AND NEW.can_credit="YES" AND NEW.amount>0) THEN
    UPDATE `deposit_addresses`
    SET `total_deposited`=`total_deposited`+NEW.amount, `numb_deposit`=`numb_deposit`+1
    WHERE `api_id`=NEW.api_id AND `coin_name`=NEW.coin_name AND (`address`=NEW.address OR (`address_extra`=NEW.extra AND NEW.extra IS NOT NULL)) LIMIT 1;
  END IF;
END;;

DELIMITER ;

DROP TABLE IF EXISTS `deposit_addresses`;
CREATE TABLE `deposit_addresses` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `api_id` int(11) NOT NULL,
  `coin_name` varchar(32) NOT NULL,
  `created_date` int(11) NOT NULL,
  `address` varchar(256) NOT NULL,
  `address_extra` varchar(64) DEFAULT NULL,
  `private_key` text DEFAULT NULL,
  `tag` varchar(1024) DEFAULT NULL,
  `second_tag` varchar(512) DEFAULT NULL,
  `total_deposited` float NOT NULL DEFAULT 0,
  `numb_deposit` int(11) NOT NULL DEFAULT 0,
  `total_received` float NOT NULL DEFAULT 0,
  `numb_received` int(11) NOT NULL DEFAULT 0,
  `total_sent` float NOT NULL DEFAULT 0,
  `numb_sent` int(11) NOT NULL DEFAULT 0,
  `total_withdrew` float NOT NULL DEFAULT 0,
  `numb_withdrew` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `api_id_coin_name_tag` (`api_id`,`coin_name`,`tag`) USING HASH,
  KEY `api_id` (`api_id`),
  KEY `coin_name` (`coin_name`),
  KEY `tag` (`tag`(768)),
  KEY `second_tag` (`second_tag`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


DROP TABLE IF EXISTS `transfer_records`;
CREATE TABLE `transfer_records` (
  `tr_id` bigint(20) NOT NULL AUTO_INCREMENT,
  `api_id` int(11) NOT NULL,
  `from_address` varchar(256) NOT NULL,
  `to_address` varchar(256) NOT NULL,
  `amount` float NOT NULL,
  `coin_name` varchar(32) NOT NULL,
  `purpose` text NOT NULL,
  `timestamp` int(11) NOT NULL,
  `ref_uuid` varchar(128) NOT NULL,
  PRIMARY KEY (`tr_id`),
  KEY `api_id` (`api_id`),
  KEY `from_dep_id` (`from_address`),
  KEY `to_dep_id` (`to_address`),
  KEY `coin_name` (`coin_name`),
  KEY `timestamp` (`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


DELIMITER ;;

CREATE TRIGGER `transfer_records_to_deposit` AFTER INSERT ON `transfer_records` FOR EACH ROW
BEGIN
  UPDATE `deposit_addresses`
  SET `total_received`=`total_received`+NEW.amount, `numb_received`=`numb_received`+1
  WHERE `address`=NEW.to_address AND `coin_name`=NEW.coin_name LIMIT 1;

  UPDATE `deposit_addresses`
  SET `total_sent`=`total_sent`+NEW.amount, `numb_sent`=`numb_sent`+1
  WHERE `address`=NEW.from_address AND `coin_name`=NEW.coin_name LIMIT 1;
END;;

DELIMITER ;

DROP TABLE IF EXISTS `withdraws`;
CREATE TABLE `withdraws` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `api_id` int(11) NOT NULL,
  `coin_name` varchar(32) NOT NULL,
  `from_address` varchar(256) NOT NULL,
  `amount` float NOT NULL,
  `fee_and_tax` float NOT NULL DEFAULT 0,
  `from_deposit_id` int(11) NOT NULL DEFAULT 0,
  `to_address` varchar(256) NOT NULL,
  `txid` varchar(256) NOT NULL,
  `tx_key` text DEFAULT NULL,
  `timestamp` int(11) NOT NULL,
  `success` tinyint(4) NOT NULL DEFAULT 1,
  `remark` text DEFAULT NULL,
  `ref_uuid` varchar(128) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `api_id` (`api_id`),
  KEY `coin_name` (`coin_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


DELIMITER ;;

CREATE TRIGGER `withdraws_to_deposits` AFTER INSERT ON `withdraws` FOR EACH ROW
BEGIN
  UPDATE `deposit_addresses`
  SET `total_withdrew`=`total_withdrew`+NEW.amount+NEW.fee_and_tax, `numb_withdrew`=`numb_withdrew`+1
  WHERE `api_id`=NEW.api_id AND `coin_name`=NEW.coin_name AND `address`=NEW.from_address LIMIT 1;
END;;

DELIMITER ;

-- 2024-03-28 09:21:40