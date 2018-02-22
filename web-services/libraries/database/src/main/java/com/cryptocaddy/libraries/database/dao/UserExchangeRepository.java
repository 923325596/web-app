package com.cryptocaddy.libraries.database.dao;

import org.springframework.data.repository.CrudRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface UserExchangeRepository extends CrudRepository<UserExchange, String> {

    UserExchange findByUser(User user);

}