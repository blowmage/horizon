#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


from django.core.urlresolvers import reverse
from django import http
from mox import IsA  # noqa

from openstack_dashboard import api
from openstack_dashboard.dashboards.admin.aggregates import constants
from openstack_dashboard.dashboards.admin.aggregates import workflows
from openstack_dashboard.test import helpers as test


class BaseAggregateWorkflowTests(test.BaseAdminViewTests):

    def _get_create_workflow_data(self, aggregate, hosts=None):
        aggregate_info = {"name": aggregate.name,
                          "availability_zone": aggregate.availability_zone}

        if hosts:
            compute_hosts = []
            for host in hosts:
                if host.service == 'compute':
                    compute_hosts.append(host)

            host_field_name = 'add_host_to_aggregate_role_member'
            aggregate_info[host_field_name] = \
                [h.host_name for h in compute_hosts]

        return aggregate_info

    def _get_manage_workflow_data(self, aggregate, hosts=None, ):
        aggregate_info = {"id": aggregate.id}

        if hosts:
            compute_hosts = []
            for host in hosts:
                if host.service == 'compute':
                    compute_hosts.append(host)

            host_field_name = 'add_host_to_aggregate_role_member'
            aggregate_info[host_field_name] = \
                [h.host_name for h in compute_hosts]

        return aggregate_info


class CreateAggregateWorkflowTests(BaseAggregateWorkflowTests):

    @test.create_stubs({api.nova: ('host_list', ), })
    def test_workflow_get(self):

        api.nova.host_list(IsA(http.HttpRequest)).AndReturn(self.hosts.list())
        self.mox.ReplayAll()

        url = reverse(constants.AGGREGATES_CREATE_URL)
        res = self.client.get(url)
        workflow = res.context['workflow']

        self.assertTemplateUsed(res, constants.AGGREGATES_CREATE_VIEW_TEMPLATE)
        self.assertEqual(workflow.name, workflows.CreateAggregateWorkflow.name)
        self.assertQuerysetEqual(workflow.steps,
                        ['<SetAggregateInfoStep: set_aggregate_info>',
                        '<AddHostsToAggregateStep: add_host_to_aggregate>'])

    @test.create_stubs({api.nova: ('host_list', 'aggregate_details_list',
                                   'aggregate_create'), })
    def test_create_aggregate(self):

        aggregate = self.aggregates.first()

        api.nova.host_list(IsA(http.HttpRequest)).AndReturn(self.hosts.list())
        api.nova.aggregate_details_list(IsA(http.HttpRequest)).AndReturn([])

        workflow_data = self._get_create_workflow_data(aggregate)
        api.nova.aggregate_create(IsA(http.HttpRequest),
                                  name=workflow_data['name'],
                                  availability_zone=
                                  workflow_data['availability_zone'])\
            .AndReturn(aggregate)

        self.mox.ReplayAll()

        url = reverse(constants.AGGREGATES_CREATE_URL)
        res = self.client.post(url, workflow_data)

        self.assertNoFormErrors(res)
        self.assertRedirectsNoFollow(res,
                                     reverse(constants.AGGREGATES_INDEX_URL))

    @test.create_stubs({api.nova: ('host_list',
                                   'aggregate_details_list',
                                   'aggregate_create',
                                   'add_host_to_aggregate'), })
    def test_create_aggregate_with_hosts(self):

        aggregate = self.aggregates.first()
        hosts = self.hosts.list()

        api.nova.host_list(IsA(http.HttpRequest)).AndReturn(self.hosts.list())
        api.nova.aggregate_details_list(IsA(http.HttpRequest)).AndReturn([])

        workflow_data = self._get_create_workflow_data(aggregate, hosts)
        api.nova.aggregate_create(IsA(http.HttpRequest),
                                  name=workflow_data['name'],
                                  availability_zone=
                                  workflow_data['availability_zone'])\
            .AndReturn(aggregate)

        compute_hosts = []
        for host in hosts:
            if host.service == 'compute':
                compute_hosts.append(host)

        for host in compute_hosts:
            api.nova.add_host_to_aggregate(IsA(http.HttpRequest),
                                           aggregate.id, host.host_name)

        self.mox.ReplayAll()

        url = reverse(constants.AGGREGATES_CREATE_URL)
        res = self.client.post(url, workflow_data)

        self.assertNoFormErrors(res)
        self.assertRedirectsNoFollow(res,
                                     reverse(constants.AGGREGATES_INDEX_URL))

    @test.create_stubs({api.nova: ('host_list', 'aggregate_details_list', ), })
    def test_host_list_nova_compute(self):

        hosts = self.hosts.list()
        compute_hosts = []

        for host in hosts:
            if host.service == 'compute':
                compute_hosts.append(host)

        api.nova.host_list(IsA(http.HttpRequest)).AndReturn(self.hosts.list())

        self.mox.ReplayAll()

        url = reverse(constants.AGGREGATES_CREATE_URL)
        res = self.client.get(url)
        workflow = res.context['workflow']
        step = workflow.get_step("add_host_to_aggregate")
        field_name = step.get_member_field_name('member')
        self.assertEqual(len(step.action.fields[field_name].choices),
                         len(compute_hosts))


class AggregatesViewTests(test.BaseAdminViewTests):

    @test.create_stubs({api.nova: ('aggregate_details_list',
                                   'availability_zone_list',), })
    def test_index(self):
        api.nova.aggregate_details_list(IsA(http.HttpRequest)) \
                .AndReturn(self.aggregates.list())
        api.nova.availability_zone_list(IsA(http.HttpRequest), detailed=True) \
                .AndReturn(self.availability_zones.list())
        self.mox.ReplayAll()

        res = self.client.get(reverse(constants.AGGREGATES_INDEX_URL))
        self.assertTemplateUsed(res, constants.AGGREGATES_INDEX_VIEW_TEMPLATE)
        self.assertItemsEqual(res.context['host_aggregates_table'].data,
                              self.aggregates.list())
        self.assertItemsEqual(res.context['availability_zones_table'].data,
                              self.availability_zones.list())

    @test.create_stubs({api.nova: ('aggregate_update', 'aggregate_get',), })
    def _test_generic_update_aggregate(self, form_data, aggregate,
                                       error_count=0,
                                       expected_error_message=None):
        api.nova.aggregate_get(IsA(http.HttpRequest), str(aggregate.id))\
                .AndReturn(aggregate)
        if not expected_error_message:
            az = form_data['availability_zone']
            aggregate_data = {'name': form_data['name'],
                              'availability_zone': az}
            api.nova.aggregate_update(IsA(http.HttpRequest), str(aggregate.id),
                                      aggregate_data)
        self.mox.ReplayAll()

        res = self.client.post(reverse(constants.AGGREGATES_UPDATE_URL,
                               args=[aggregate.id]),
                               form_data)

        if not expected_error_message:
            self.assertNoFormErrors(res)
            self.assertRedirectsNoFollow(res,
                    reverse(constants.AGGREGATES_INDEX_URL))
        else:
            self.assertFormErrors(res, error_count, expected_error_message)

    def test_update_aggregate(self):
        aggregate = self.aggregates.first()
        form_data = {'id': aggregate.id,
                     'name': 'my_new_name',
                     'availability_zone': 'my_new_zone'}

        self._test_generic_update_aggregate(form_data, aggregate)

    def test_update_aggregate_fails_missing_fields(self):
        aggregate = self.aggregates.first()
        form_data = {'id': aggregate.id}

        self._test_generic_update_aggregate(form_data, aggregate, 1,
                                            u'This field is required')


class ManageHostsTests(test.BaseAdminViewTests):

    def test_manage_hosts(self):
        aggregate = self.aggregates.first()
        res = self.client.get(reverse(constants.AGGREGATES_MANAGE_HOSTS_URL,
                                      args=[aggregate.id]))
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res,
                                constants.AGGREGATES_MANAGE_HOSTS_TEMPLATE)

    @test.create_stubs({api.nova: ('aggregate_get', 'add_host_to_aggregate',
                                   'host_list')})
    def test_manage_hosts_update_empty_aggregate(self):
        aggregate = self.aggregates.first()
        aggregate.hosts = []
        host = self.hosts.get(service="compute")

        form_data = {'manageaggregatehostsaction_role_member':
                     [host.host_name]}

        api.nova.aggregate_get(IsA(http.HttpRequest), str(aggregate.id)) \
                .AndReturn(aggregate)
        api.nova.host_list(IsA(http.HttpRequest)) \
                .AndReturn(self.hosts.list())
        api.nova.aggregate_get(IsA(http.HttpRequest), str(aggregate.id)) \
                .AndReturn(aggregate)
        api.nova.add_host_to_aggregate(IsA(http.HttpRequest),
                                       str(aggregate.id), host.host_name)
        self.mox.ReplayAll()

        res = self.client.post(reverse(constants.AGGREGATES_MANAGE_HOSTS_URL,
                                       args=[aggregate.id]),
                               form_data)

        self.assertNoFormErrors(res)
        self.assertRedirectsNoFollow(res,
                                     reverse(constants.AGGREGATES_INDEX_URL))
