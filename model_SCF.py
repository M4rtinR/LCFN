## baseline: Spectral Collaborative Filtering (SCF)
## Lei Zheng, Chun-Ta Lu, Fei Jiang, Jiawei Zhang, and Philip S. Yu. Spectral collaborative filtering. In Proceedings of the 12th ACM Conference on Recommender Systems, RecSys '18, pages 311-319, 2018.

import tensorflow.compat.v1 as tf
tf.disable_v2_behavior()
import numpy as np

class model_SCF(object):
    def __init__(self, layer, n_users, n_items, emb_dim, lr, lamda, pre_train_latent_factor, if_pretrain, sparse_graph):
        self.model_name = 'SCF'
        self.n_users = n_users
        self.n_items = n_items
        self.emb_dim = emb_dim
        self.layer = layer
        self.lamda = lamda
        self.lr = lr
        [self.U, self.V] = pre_train_latent_factor
        self.if_pretrain = if_pretrain
        self.A_hat = sparse_graph

        # placeholder definition
        self.users = tf.placeholder(tf.int32, shape=(None,))
        self.pos_items = tf.placeholder(tf.int32, shape=(None,))
        self.neg_items = tf.placeholder(tf.int32, shape=(None,))
        self.keep_prob = tf.placeholder(tf.float32, shape=(None))
        self.items_in_train_data = tf.placeholder(tf.float32, shape=(None, None))
        self.top_k = tf.placeholder(tf.int32, shape=(None))

        if self.if_pretrain:
            self.user_embeddings = tf.Variable(self.U, name='user_embeddings')
            self.item_embeddings = tf.Variable(self.V, name='item_embeddings')
        else:
            self.user_embeddings = tf.Variable(
                tf.random_normal([self.n_users, self.emb_dim], mean=0.01, stddev=0.02, dtype=tf.float32),
                name='user_embeddings')
            self.item_embeddings = tf.Variable(
                tf.random_normal([self.n_items, self.emb_dim], mean=0.01, stddev=0.02, dtype=tf.float32),
                name='item_embeddings')

        self.filters = []
        for l in range(self.layer):
            self.filters.append(
                tf.Variable((np.random.normal(0, 0.001, (self.emb_dim, self.emb_dim)) + np.diag(np.random.normal(1, 0.001, self.emb_dim))).astype(np.float32))
            )

        embeddings = tf.concat([self.user_embeddings, self.item_embeddings], axis=0)
        all_embeddings = [embeddings]
        for l in range(self.layer):
            ## convolution of embedding: (U*U^T+U*\Lambda*U^T)*emb = (I+L)*emb = (2*I-D^{-1}*A)*emb = 2*emb-H_hat*emb
            embeddings = 2 * embeddings - tf.sparse_tensor_dense_matmul(self.A_hat, embeddings)
            embeddings = tf.nn.sigmoid(tf.matmul(embeddings, self.filters[l]))
            all_embeddings += [embeddings]
        all_embeddings = tf.concat(all_embeddings, 1)
        self.user_all_embeddings, self.item_all_embeddings = tf.split(all_embeddings, [self.n_users, self.n_items], 0)

        self.u_embeddings = tf.nn.embedding_lookup(self.user_all_embeddings, self.users)
        self.pos_i_embeddings = tf.nn.embedding_lookup(self.item_all_embeddings, self.pos_items)
        self.neg_i_embeddings = tf.nn.embedding_lookup(self.item_all_embeddings, self.neg_items)

        self.loss = self.create_bpr_loss(self.u_embeddings, self.pos_i_embeddings, self.neg_i_embeddings)
        self.opt = tf.train.RMSPropOptimizer(learning_rate=self.lr)
        self.updates = self.opt.minimize(self.loss, var_list=[self.user_embeddings, self.item_embeddings] + self.filters)

        self.all_ratings = tf.matmul(self.u_embeddings, self.item_all_embeddings, transpose_a=False, transpose_b=True)
        self.all_ratings += self.items_in_train_data  ## set a very small value for the items appearing in the training set to make sure they are at the end of the sorted list
        self.top_items = tf.nn.top_k(self.all_ratings, k=self.top_k, sorted=True).indices

    def create_bpr_loss(self, users, pos_items, neg_items):
        pos_scores = tf.reduce_sum(tf.multiply(users, pos_items), axis=1)
        neg_scores = tf.reduce_sum(tf.multiply(users, neg_items), axis=1)
        regularizer = tf.nn.l2_loss(users) + tf.nn.l2_loss(pos_items) + tf.nn.l2_loss(neg_items)
        maxi = tf.log(tf.nn.sigmoid(pos_scores - neg_scores))
        loss = tf.negative(tf.reduce_sum(maxi)) + self.lamda * regularizer
        return loss